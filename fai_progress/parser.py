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
import binascii
import re
from base64 import b64decode
from gettext import gettext as _


class LineParser():
    """
    A basic parser for any line of interest in the log of a FAI run.
    This is also the base class for all more specific parsers.

    The basic idea is to match a regular expression against a line and to react
    on the result. Therefore the process method calls on a match the _on_match
    method with the named capturing groups as arguments.

    The default implementation of the _on_match method inserts the named
    capuring groups into a message_tamplates and updates the progress via the
    call_back function.
    """

    def __init__(self, call_back, message_template, pattern, recurring,
                 expected_hits=1):
        """
        The message template can contain named braces. The regex has to contain
        named capturing groups with the same names.
        :param call_back:callable propagate matches to this fai progress object
        :param message_template:str message template for a message to display
        :param pattern:str regular expression for a line of interest
        :param recurring:
        :param expected_hits:
        :raises KeyError: if field names in template string do not have
          corresponding groups in regex
        """
        self.message_template = message_template
        self.pattern = re.compile(pattern)
        self.recurring = recurring
        self.expected_hits = expected_hits

        # make sure fields in template match groups in regex
        self.message_template.format_map(self.pattern.groupindex)

        self.call_back = call_back
        assert (callable(self.call_back))

        self.match = None
        self.hits = 0

    def process(self, line):
        self.match = self.pattern.match(line)
        if self.match:
            self.hits += 1
            self._on_match(**self.match.groupdict())

    def _on_match(self, **values):
        message = self.message_template.format_map(values)
        self.call_back(message, **values)


class HangupParser(LineParser):
    def __init__(self, call_back):
        regex = "^fai-progress: hangup$"
        super(HangupParser, self).__init__(call_back, "", regex,
                                           recurring=False, expected_hits=1)


class LDAP2FaiErrorParser(LineParser):
    def __init__(self, call_back):
        message_template = "ldap2fai-error: {message}"
        regex = "^ldap2fai-error:(?P<message>.*)$"
        super(LDAP2FaiErrorParser, self).__init__(call_back, message_template,
                                                  regex, recurring=False,
                                                  expected_hits=0)

    def _on_match(self, **values):
        try:
            self.call_back.handle_error(self.message_template.format(
                b64decode(self.match.group("message"))))
        except binascii.Error:
            self.call_back.handle_error(_(
                "ldap2fai-error occurred, however the cause could not be"
                " decoded!"))
