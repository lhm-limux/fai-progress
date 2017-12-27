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


from unittest import TestCase

from fai_progress.parser import BasicLineParser


class CallBackMockup():

    def __init__(self):
        self.message = None

    def update_message(self, message):
        self.message = message


class TestBasicLineParser(TestCase):

    message = "Test-Message"
    message_template = "Test-Message: {test}"
    simple_regex = "^.+$"
    template_regex = "^(?P<test>.+)$"
    simple_line = "Working in normal parameters."

    def setUp(self):
        self.call_back = CallBackMockup()

    def test_plain(self):
        basic_line_parser = BasicLineParser(self.call_back,
                                            self.message,
                                            self.simple_regex)
        basic_line_parser.process(self.simple_line)
        self.assertEqual(self.call_back.message,
                         self.message)

    def test_regexp(self):
        basic_line_parser = BasicLineParser(self.call_back,
                                            self.message_template,
                                            self.template_regex)
        basic_line_parser.process(self.simple_line)
        self.assertEqual(self.call_back.message,
                         self.message_template.format(test=self.simple_line))

    def test_message_template_keyword_not_in_regexp(self):
        self.assertRaises(KeyError,
                          BasicLineParser,
                          self.call_back,
                          self.message_template,
                          self.simple_regex)




