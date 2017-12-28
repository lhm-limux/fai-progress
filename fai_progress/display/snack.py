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


from gettext import gettext as _

from snack import SnackScreen, colorsets, Scale, Label, Textbox, Grid, Form


class SnackInterface():
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