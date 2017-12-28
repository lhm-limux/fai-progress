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
from gettext import bindtextdomain, textdomain, gettext as _
from sys import stderr, exit
from traceback import print_exc

from fai_progress.display.simple import LinePrintInterface
from fai_progress.display.snack import SnackInterface
from fai_progress.progress import FaiProgress


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

    exit_code = 0
    try:
        with open(args.input, 'r') as handle:
            fai_progress = FaiProgress(handle, display, args.input_polling_interval,
                               signal_file=args.signal_file, debug=args.debug)
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