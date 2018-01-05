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
from tempfile import mkstemp
from threading import Thread
from time import sleep

from os import remove

from fai_progress.display.simple import LinePrintInterface
from fai_progress.main import load_data
from fai_progress.progress import FaiProgress


class FaiRunMockup(Thread):

    def __init__(self, input_path, output_file, interval_sec=0.01):
        self.input_path = input_path
        self.output_file = output_file
        self.interval = interval_sec
        super(FaiRunMockup, self).__init__(daemon=True)

    def run(self):
        handle = open(self.input_path)
        content = handle.read()
        handle.close()

        with open(self.output_file, "w") as handle:
            for line in content.splitlines(keepends=False):
                print(line, file=handle)
                handle.flush()
                sleep(self.interval)



if __name__ == '__main__':
    arg_parser = ArgumentParser(prog="simulate", description="Simulate Fai-Run")
    arg_parser.add_argument("input", help="data source FAI log")
    args = arg_parser.parse_args()

    temporary_handle,temporary_file = mkstemp(prefix="simulate")

    fai_run = FaiRunMockup(args.input, temporary_file)
    fai_run.start()

    display = LinePrintInterface()

    with open(temporary_file, "r") as handle:
        progress = FaiProgress(handle, display, 0.2, debug=True)
        load_data(progress)
        progress.run()

    fai_run.join()
    temporary_handle.close()
    remove(temporary_file)