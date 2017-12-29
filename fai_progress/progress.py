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

from fai_progress.parser import BasicLineParser, FaiTaskParser, ShellParser, BootstrapPackageVersionParser, \
    BootstrapPackageParser, InstallSummaryParser, PackageReceiveParser, PackageInstallParser, HangupParser, \
    LDAP2FaiErrorParser


class FaiProgress():
    """
    Represent the progress of FAI run.
    The progress is calculated from the fai.log generated during a FAI run.
    This file is read on the fly and processed by some parsers.
    """
    def __init__(self, input_file, display, input_polling_interval, signal_file=None, debug=False):
        self.current_progress = 0
        self.current_progress_base = 0
        self.current_progress_ceiling = 0
        self.current_task = FaiTask(_("Initializing FAI"), 1, 0)
        self.current_progress_slowdown_barrier = 0
        self.action = None
        self.signal = SignalProgress(signal_file)
        self.debug_mode = debug
        self.input_file = input_file
        self.input_polling_interval = input_polling_interval
        self.display = display
        self.active = True
        self.update_message(self.current_task.description)
        self.global_parsers = [LDAP2FaiErrorParser(self), HangupParser(self)]
        self.tasks = {}

        # define tasks (ignored tasks: chboot, faiend)
        self.add_task("confdir", _("Retrieving initial client configuration"), 0.25)
        self.add_task("setup", _("Gathering client information"), 0.5)
        self.add_task("defclass", _("Defining installation classes"), 0.75)
        self.add_task("defvar", _("Defining installation variables"), 1)
        self.add_task("action", _("Evaluating action"), 1.25)
        self.add_task("install", _("Starting installation"), 1.5)
        self.add_task("partition", _("Inspecting harddisks"), 4.5)
        self.add_task("mountdisks", _("Mounting filesystems"), 5)
        self.add_task("extrbase", _("Bootstrapping base system"), 15, 5, recurring=250)
        self.add_task("debconf", _("Preparing debconf database"), 16, 6)
        self.add_task("repository", _("Fetching repository information"), 20, 10)
        self.add_task("updatebase", _("Updating base system"), 25, 65, recurring=1000)
        self.add_task("instsoft", _("Software installation"), 75, recurring=2500)
        self.add_task("configure", _("Adapting system and package configuration"), 90)
        self.add_task("tests", _("Running tests"), 95)
        self.add_task("finish", _("Finishing installation"), 98)
        self.add_task("audit", _("Audit"), 99.5)
        self.add_task("savelog", _("Installation finished"), 100)

        # add additional parsers
        self.add_parser("defvar", BasicLineParser(self, _("Starting installation"), "^FAI_ACTION: install$"))
        self.add_parser("partition", BasicLineParser(self, _("Partitioning harddisk"), "^Executing: parted"), expected_hits=10)
        self.add_parser("partition", BasicLineParser(self, _("Creating swap"), "^Executing: mkswap"), expected_hits=2)
        self.add_parser("partition", BasicLineParser(self, _("Creating filesystems"), "^Executing: mkfs"), expected_hits=10)
        self.add_parser("extrbase", BootstrapPackageVersionParser(self, "Retrieving"), recurring=True)
        self.add_parser("extrbase", BootstrapPackageVersionParser(self, "Validating"), recurring=True)
        self.add_parser("extrbase", BasicLineParser(self, _("Unpacking the base system"), "^I: Unpacking the base system..."))
        self.add_parser("extrbase", BootstrapPackageParser(self, "Extracting"), recurring=True)
        self.add_parser("extrbase", BootstrapPackageParser(self, "Unpacking"), recurring=True)
        self.add_parser("extrbase", BootstrapPackageParser(self, "Configuring"), recurring=True)
        self.add_parser("extrbase", BasicLineParser(self, _("Resolving dependencies"), "^I: Resolving dependencies$"))
        self.add_parser("extrbase", BasicLineParser(self, _("Checking repository content"), "^I: Checking component"))
        self.add_parser("instsoft", InstallSummaryParser(self))
        self.add_parser("instsoft", PackageReceiveParser(self), recurring=True)
        self.add_parser("instsoft", PackageInstallParser(self, "Unpacking"), recurring=True)
        self.add_parser("instsoft", PackageInstallParser(self, "Setting up"), recurring=True)
        self.add_parser("configure", ShellParser(self, _("Executing script {script} of class {class}")), expected_hits=20)
        self.add_parser("tests", ShellParser(self, _("Running test {script}")), expected_hits=5)

    def add_task(self, task, description, progress, progress_softupdate=None, recurring=0):
        """
        :param task:str each task is identified by this identifier
        :param description:str user readable description of the task
        :param progress:float the progress of installation in percent when this task is *finished*
        :param progress_softupdate:float analogous to progress for softupdate;
                                    leave empty if the same as for installation
        """
        self.tasks[task] = FaiTask(description, progress, progress_softupdate, recurring)
        self.global_parsers.append(FaiTaskParser(self, task, description))

    def add_parser(self, task, parser, recurring=False, expected_hits=0):
        if recurring:
            assert expected_hits == 0
        self.tasks[task].add_parser(parser, recurring, expected_hits)

    def debug_message(self, message):
        if self.debug_mode:
            self.display.debug(message)

    def update_message(self, message):
        if self.current_progress < self.current_progress_slowdown_barrier or self.debug_mode:
            self.current_progress += self.progress_step_length()
        else:
            # make sure that the progress stays in defined progress range
            range = self.current_progress_ceiling - self.current_progress_slowdown_barrier
            if range != 0:
                subprogress = (self.current_progress - self.current_progress_slowdown_barrier) / range
                panic_factor = subprogress / (subprogress + 1)
                self.current_progress += self.progress_step_length() * panic_factor
        self.display.update(self.current_progress, message)
        self.signal.signal_progress(self.current_progress)

    def next_task(self, name):
        if self.current_task is self.tasks[name]:
            # do nothing if this is already the current task
            return
        self.current_progress = self.current_progress_ceiling
        self.current_task = self.tasks[name]
        self.current_progress_base = self.current_progress
        self.current_progress_ceiling = self.current_task.get_target_progress(self.action)
        self.current_progress_slowdown_barrier = self.current_progress + \
                                                 (self.current_progress_ceiling - self.current_progress) * 0.9
        self.display.update_task(self.current_progress, name, self.current_task.description)

    def progress_step_length(self):
        range = self.current_progress_ceiling - self.current_progress_base
        return range / self.current_task.expected_steps

    def update_package_count(self, upgrades, installs, removes):
        self.current_task.update_recurrent_steps(int(upgrades) + int(installs) - int(removes))

    def update_action(self, action):
        self.action = action

    def handle_error(self, message):
        self.display.debug(message)
        self.active = False
        self.display.cleanup()

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
        for parser in self.global_parsers + self.current_task.parsers:
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


class FaiTask():
    def __init__(self, description, target_progress, progress_softupdate=None, expected_recurring_steps=0):
        """
        A FAI run is composed of sequential phases called tasks. Some parsers only are active in the
        context of a certain task.
        :param description: user readable description of the task
        :param target_progress: the progress of installation in percent when this task is *finished*
        :param progress_softupdate: analogous to progress for softupdate;
                                    leave empty if the same value applies for both
        """
        self.description = description
        self.target_progress = target_progress
        self.progress_softupdate = progress_softupdate or target_progress
        self.parsers = []
        self._recurring_step_count = 0
        self._expected_recurring_steps = expected_recurring_steps
        self._expected_non_recurring_steps = 1
        self.expected_steps = 1

    def _update_expected_steps(self):
        expected_recurring_steps = self._recurring_step_count * self._expected_recurring_steps
        self.expected_steps = expected_recurring_steps + self._expected_non_recurring_steps

    def add_parser(self, parser, recurring_step_parser=False, expected_hits=0):
        self.parsers.append(parser)
        if recurring_step_parser:
            self._recurring_step_count += 1
        else:
            self._expected_non_recurring_steps += expected_hits
        self._update_expected_steps()

    def update_recurrent_steps(self, count):
        self._expected_recurring_steps = count
        self._update_expected_steps()

    def get_target_progress(self, action=None):
        if action and action == "softupdate":
            return self.progress_softupdate
        return self.target_progress


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
        with open(self.path, "w") as handle:
            while True:
                message = self.message_queue.get()
                if message is not None:
                    print(message, file=handle)
                    handle.flush()
                else:
                    break


