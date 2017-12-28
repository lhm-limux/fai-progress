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

from sys import stderr


class LinePrintInterface(object):
    def update_task(self, percent, task, description):
        self.update(percent, "{} ({})".format(description, task))

    def update(self, percent, text=None):
        print("[{:5.1f}%] {}".format(percent, text or ""))

    def debug(self, message):
        print("[DEBUG] {}".format(message), file=stderr)

    def cleanup(self):
        pass

