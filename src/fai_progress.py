#!/usr/bin/python3 -Es
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


from argparse import ArgumentParser
from time import sleep
from sys import exit, stderr
from snack import Scale, Form, Textbox, SnackScreen, Grid, Label, colorsets
from base64 import b64decode, binascii
from traceback import print_exc
from threading import Thread
from queue import Queue
from gettext import gettext as _
from gettext import bindtextdomain, textdomain
import os
import re


class FaiProgress(object):
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
        self.current_progress += self.progress_step_length()
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
        with open(self.input_file) as handle:
            while self.active:
                self.active = os.path.exists(self.input_file)
                line = handle.readline()
                if not line:
                    sleep(self.input_polling_interval)
                    continue
                line = line.rstrip()
                # if self.debug:
                #    self.display.debug(line)
                yield line


class FaiTask(object):
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


class BasicLineParser(object):
    """
    A basic parser for any line of interest in the log of a FAI run.
    This is also the base class for all more specific parsers.

    The basic idea is to match a regular expression against a line and to react on the result.
    Therefore the process method calls on a match the _on_match method with the named
    capturing groups as arguments.

    The default implementation of the _on_match method inserts the named capuring groups into
    a message_tamplates and updates the message via the call_back object.

    Derived classes can overwrite the _on_match method to achieve a different behaviour.
    """
    def __init__(self, call_back, message_template, regex):
        """
        The message template can contain named braces. The regex has to contain named capturing groups
        with the same names.
        :param message_template:str message template for a message to display
        :param regex:str regular expression for a line of interest
        :param call_back:FaiProgress propagate matches to this fai progress object
        """
        self.message_template = message_template
        self.pattern = re.compile(regex)
        self.call_back = call_back
        self.match = None
        self.hits = 0

    def process(self, line):
        self.match = self.pattern.match(line)
        if self.match:
            self.hits += 1
            self._on_match(**self.match.groupdict())

    def _on_match(self, **values):
        message = self.message_template.format_map(values)
        self.call_back.update_message(message)


class FaiTaskParser(BasicLineParser):
    def __init__(self, call_back, name, message_template):
        regex = "^((Skip|Call)ing task_|(Calling|Source) hook: )(?P<name>{})".format(name)
        super(FaiTaskParser, self).__init__(call_back, message_template, regex)

    def _on_match(self, **values):
        self.call_back.next_task(**values)


class ShellParser(BasicLineParser):
    def __init__(self, call_back, message_template):
        regex = "^Executing +shell: (?P<class>[^/]+)/(?P<script>[^/]+)"
        super(ShellParser, self).__init__(call_back, message_template, regex)


class BootstrapPackageVersionParser(BasicLineParser):
    def __init__(self, call_back, action):
        message_template = _(action) + " {package} {version}"
        regex = "^I: " + action + " (?P<package>.+) (?P<version>.+)$"
        super(BootstrapPackageVersionParser, self).__init__(call_back, message_template, regex)


class BootstrapPackageParser(BasicLineParser):
    def __init__(self, call_back, action):
        message_template = _(action) + " {package}"
        regex = "^I: " + action + " (?P<package>.+)...$"
        super(BootstrapPackageParser, self).__init__(call_back, message_template, regex)


class InstallSummaryParser(BasicLineParser):
    def __init__(self, call_back):
        message = _("Gathering information for package lists")
        regex = "(?P<upgrades>[0-9]+)(?: packages)? upgraded, (?P<installs>[0-9]+) newly installed, (?P<removes>[0-9]+) to remove"
        super(InstallSummaryParser, self).__init__(call_back, message, regex)

    def _on_match(self, **values):
        self.call_back.update_package_count(**values)


class PackageReceiveParser(BasicLineParser):
    def __init__(self, call_back):
        message_template = _("Retrieving") + " {package} {version} ..."
        regex = "^Get:\s?(?P<number>[0-9]+) [^ ]+ [^ ]+ [^ ]+ (?P<package>[^ ]+) [^ ]+ (?P<version>[^ ]+) [^ ]+"
        super(PackageReceiveParser, self).__init__(call_back, message_template, regex)


class PackageInstallParser(BasicLineParser):
    def __init__(self, call_back, action):
        # PackageInstallParser.instances = PackageInstallParser.instances + 1
        message_template = _(action) + " {package} ..."
        regex = "^" + action + " (?P<package>[^ ]+) .* ..."
        super(PackageInstallParser, self).__init__(call_back, message_template, regex)


class FaiActionParser(BasicLineParser):
    def __init__(self, call_back):
        regex = "^FAI_ACTION: (?P<action>[^ ]+)"
        super(FaiActionParser, self).__init__(call_back, "", regex)

    def _on_match(self, **values):
        self.call_back.update_action(**values)


class HangupParser(BasicLineParser):
    def __init__(self, call_back):
        regex = "^fai-progress: hangup$"
        super(HangupParser, self).__init__(call_back, "", regex)

    def _on_match(self, **values):
        self.call_back.active = False


class LDAP2FaiErrorParser(BasicLineParser):
    def __init__(self, call_back):
        message_template = "ldap2fai-error: {}"
        regex = "^ldap2fai-error:(.*)$"
        super(LDAP2FaiErrorParser, self).__init__(call_back, message_template, regex)

    def _on_match(self, **values):
        try:
            self.call_back.handle_error(self.message_template.format(b64decode(self.match.group(1))))
        except binascii.Error:
            self.call_back.handle_error(_("ldap2fai-error occurred, however the cause could not be decoded!"))


class LinePrintInterface(object):
    def update_task(self, percent, task, description):
        self.update(percent, "{} ({})".format(description, task))

    def update(self, percent, text=None):
        print("[{:5.1f}%] {}".format(percent, text or ""))

    def debug(self, message):
        print("[DEBUG] {}".format(message), file=stderr)

    def cleanup(self):
        pass


class SnackInterface(object):
    def __init__(self, margin, title, message=None, vendor_text=None, args=None):
        self.debug_mode = args is not None and args.debug

        self.screen = SnackScreen()

        # set usual colors
        for i in colorsets["ROOT"], colorsets["ROOTTEXT"], colorsets["HELPLINE"], colorsets["EMPTYSCALE"]:
            self.screen.setColor(i, "white", "blue") if not self.debug_mode else \
                self.screen.setColor(i, "brightgreen", "black")

        # remove silly default help text
        self.screen.popHelpLine()

        # write static messages
        self.screen.drawRootText((self.screen.width - len(message)) // 2, 4, message)
        self.screen.drawRootText(-len(vendor_text) - 2, -2, vendor_text)

        if self.debug_mode:
            # write some static debug information
            self.screen.drawRootText(1, 1, _("DEBUG MODE"))
            self.screen.drawRootText(2, 2, "screen {}×{}".format(self.screen.width, self.screen.height))
            self.screen.drawRootText(2, 3, "file {}".format(args.input))

        self.window_width = self.screen.width - margin * 2

        # assemble our progress bar
        self.scale = Scale(self.window_width, 100)
        self.spacer = Label("")
        self.taskbox = Textbox(self.window_width - 2, 1, "")
        self.messagebox = Textbox(self.window_width - 8, 1, " . . . ")

        self.grid = Grid(1, 4)
        self.grid.setField(self.scale, 0, 0)
        self.grid.setField(self.spacer, 0, 1)
        self.grid.setField(self.taskbox, 0, 2)
        self.grid.setField(self.messagebox, 0, 3)
        self.grid.place(1, 1)

        self.screen.gridWrappedWindow(self.grid, title)
        self.form = Form()
        self.form.add(self.scale)
        self.form.add(self.taskbox)
        self.form.add(self.messagebox)
        self.form.draw()
        self.screen.refresh()

    def update_task(self, percent, task, description):
        self.taskbox.setText(description)
        self.update(percent, "")

    def update(self, percent, text=None):
        progress = int(percent)
        self.scale.set(progress)
        self.form.draw()
        self.screen.refresh()
        if text is not None:
            self.messagebox.setText(text)
            self.form.draw()
            self.screen.refresh()

    def debug(self, message):
        self.screen.popHelpLine()
        self.screen.pushHelpLine("[DEBUG] {}".format(message))
        self.screen.refresh()

    def cleanup(self):
        self.screen.popWindow()
        self.screen.finish()


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


def command_line_interface():
    bindtextdomain('fai-progress')
    textdomain('fai-progress')

    arg_parser = ArgumentParser(prog="fai-progress", description=_("Display progress of a FAI run"))

    arg_parser.add_argument("input", help=_("data source FAI log"))
    arg_parser.add_argument("-f", "--frontend", choices=["lineprint", "snack"], help=_("choose frontend"))
    arg_parser.add_argument("-d", "--debug", action="store_true", default=False, help="turn debugging mode on")
    arg_parser.add_argument("-m", "--message", default=_("Do not power off or unplug your machine!"),
                            help=_("this message will be displayed during fai run"))
    arg_parser.add_argument("-l", "--vendor", default="", help=_("vendor to display"))
    arg_parser.add_argument("-a", "--action", default="Install", help=_("action to display (install or update)"))
    arg_parser.add_argument("-i", "--input-polling-interval", default=0.05, type=float, help=_("wait this amount of time in seconds before read line retry"))
    arg_parser.add_argument("-s", "--signal-file", help=_("signal current progress to this path"))

    args = arg_parser.parse_args()

    if args.frontend == "lineprint":
        display = LinePrintInterface()
    else:  # if args.frontend == "snack":
        display = SnackInterface(margin=3,
                                 title=_(args.action),
                                 message=args.message,
                                 vendor_text=args.vendor,
                                 args=args)

    fai_progress = FaiProgress(args.input, display, args.input_polling_interval,
                               signal_file=args.signal_file, debug=args.debug)

    exit_code = 0
    try:
        fai_progress.run()
    except FileNotFoundError as e:
        exit_code = 1
        display.cleanup()
        print(e.strerror, e.filename, file=stderr)
    except Exception as e:
        exit_code = 2
        display.cleanup()
        print(_("Error in fai-progress"), file=stderr)
        print_exc()

    exit(exit_code)

if __name__ == '__main__':
    command_line_interface()
