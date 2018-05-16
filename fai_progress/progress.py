# coding=utf-8

# Copyright (C) 2017 Max Harmathy <max.harmathy@web.de>
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program. If not, see <http://www.gnu.org/licenses/>.


import os
from gettext import gettext as _
from queue import Queue
from threading import Thread
from time import sleep

from fai_progress.parser import LDAP2FaiErrorParser, HangupParser, LineParser


class FaiTask():
    def __init__(self, name, description, target_progress,
                 progress_softupdate=None, expected_recurring_steps=0):
        """
        A FAI run is composed of sequential phases called tasks. Some parsers
        only are active in the context of a certain task.
        :param description: user readable description of the task
        :param target_progress: the progress of installation in percent when
          this task is *finished*
        :param progress_softupdate: analogous to progress for softupdate. If
          None is give the value target_progress will be used.
        :param expected_recurring_steps:int Estimate the number of recurring
         steps in this task, e.g. expected number of packages to be installed in
         an install task. This value is the basis for the progress calculation
         if there is no possibility to parser the number steps i.e. installed
         packages e.g. in the deboostrap phase.
        """
        self.name = name
        self.description = description

        self.parsers = []

        self.subscribers = []

        self.target_progress = target_progress
        self.progress_softupdate = progress_softupdate or target_progress

        self.steps = 0
        self.expected_steps = expected_recurring_steps
        self._expected_recurring_steps = expected_recurring_steps
        self._expected_non_recurring_steps = 0
        self._recurring_factor = 0

    def get_task_parser(self, call_back):
        """
        Generate a parser object for recognising this particular task in the
        fai.log.
        :param call_back: function which gets called on a match
        :return: parser object
        """
        return LineParser(
            call_back,
            self.description,
            "^((Skip|Call)ing task_|(Calling|Source) hook: )(?P<name>{})"
                .format(self.name),
            recurring=False
        )

    def subscribe(self, subscriber):
        self.subscribers.append(subscriber)

    def install_parser(self, action, **parameters):
        parser = LineParser(self.__getattribute__(action), **parameters)
        if parser.recurring:
            self._expected_recurring_steps += parser.expected_hits
            self._recurring_factor += 1
        else:
            self._expected_non_recurring_steps += parser.expected_hits
        self._update_expected_steps()
        self.parsers.append(parser)

    def _update_expected_steps(self):
        self.expected_steps = self._expected_non_recurring_steps + \
            self._expected_recurring_steps * self._recurring_factor

    def get_target_progress(self, action=None):
        if action and action == "softupdate":
            return self.progress_softupdate
        return self.target_progress

    def get_progress(self):
        if self.expected_steps == 0:
            # avoid division by zero
            return 1
        # cut off any progress over 1
        return min(self.steps / self.expected_steps, 1)

    def update_progress(self, message, **values):
        self.steps += 1
        for subscriber in self.subscribers:
            subscriber.update_progress(message)

    def update_action(self, message, action):
        self.steps += 1
        for subscriber in self.subscribers:
            subscriber.update_action(action)
            subscriber.update_progress(message)

    def update_package_count(self, message, upgrades, installs, removes):
        self._expected_recurring_steps = int(upgrades)
        self._expected_recurring_steps += int(installs)
        self._expected_recurring_steps += int(removes)
        for subscriber in self.subscribers:
            subscriber.update_progress(message)


class FaiProgress():
    """
    Represent the progress of FAI run.
    The progress is calculated from the fai.log generated during a FAI run.
    This file is read on the fly and processed by some parsers.
    """

    def __init__(self, input_file, display, input_polling_interval,
                 signal_file=None, debug=False):
        self.progress_base = 0
        self.progress = 0
        self.task = FaiTask(_("Initializing FAI"), 1, 0)
        self.task_range = 0
        self.registered_tasks = {}
        self.action = None
        self.signal = SignalProgress(signal_file)
        self.debug_mode = debug
        self.input_file = input_file
        self.input_polling_interval = input_polling_interval
        self.display = display
        self.active = True
        self.global_parsers = [
            LDAP2FaiErrorParser(self.handle_error),
            HangupParser(self.deactivate),
        ]

    def add_task(self, task):
        self.registered_tasks[task.name] = task
        task.subscribe(self)
        self.global_parsers.append(task.get_task_parser(self.next_task))

    def debug_message(self, message):
        if self.debug_mode:
            self.display.debug(message)

    def update_progress(self, message):
        self.progress = self.progress_base + \
                        self.task_range * self.task.get_progress()
        self.display.update(self.progress, message)
        self.signal.signal_progress(self.progress)

    def next_task(self, message, name):
        if self.task.name == name:
            # do nothing if this is already the current task
            return
        # current task is finished, set progress to its target
        self.progress = self.task.get_target_progress(self.action)
        self.progress_base = self.progress
        # prepare for new task
        self.task = self.registered_tasks[name]
        self.task_range = self.task.get_target_progress(
            self.action) - self.progress_base
        self.display.update_task(self.progress, name, self.task.description)

    def update_action(self, action):
        self.action = action

    def handle_error(self, message, **kwargs):
        self.display.debug(message)
        self.active = False
        self.display.cleanup()

    def deactivate(self, **kwargs):
        self.active = False

    def run(self):
        self.signal.start()
        for line in self.lines():
            self.process_input(line)
        self.display.update_task(100, "faiend", _("Finished"))
        self.display.cleanup()
        self.signal.deactivate()
        self.signal.join()

    def process_input(self, line):
        self.debug_message(line)
        for parser in self.global_parsers + self.task.parsers:
            parser.process(line)
            if parser.match:
                return

    def lines(self):
        while self.active:
            line = self.input_file.readline()
            if not line:
                sleep(self.input_polling_interval)
                continue
            line = line.rstrip()
            # if self.debug:
            #    self.display.debug(line)
            yield line


class SignalProgress(Thread):
    """
    Asynchronously write the current progress to a path.
    """

    def __init__(self, path):
        self.message_queue = Queue()
        self.path = path
        super(SignalProgress, self).__init__(daemon=True)

    def signal_progress(self, progress):
        self.message_queue.put("PROGRESS {:.1f}".format(progress))

    def deactivate(self):
        self.message_queue.put(None)

    def run(self):
        if self.path is None or not os.path.exists(self.path):
            return
        with open(self.path, "w", encoding="utf-8") as handle:
            while True:
                message = self.message_queue.get()
                if message is not None:
                    print(message, file=handle)
                    handle.flush()
                else:
                    break
