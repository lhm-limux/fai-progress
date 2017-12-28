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


class BasicLineParser():
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
        :raises KeyError: if field names in template string do not have corresponding groups in regex
        """
        self.message_template = message_template
        self.pattern = re.compile(regex)

        # make sure fields in template match groups in regex
        self.message_template.format_map(self.pattern.groupindex)

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