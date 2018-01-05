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

import json

from fai_progress.main import resource_path, load_task_data
from fai_progress.progress import FaiTask
from fai_progress.parser import LineParser


class FaiProgressMockup():
    def __init__(self):
        self.message = None
        self.values = {}

    def update_progress(self, message, **values):
        self.message = message
        self.values = values


class TestData(TestCase):
    """
    Test provided JSON data
    """

    parser_data = None
    task_data = None

    def setUp(self):
        if self.task_data is None:
            with open(resource_path("tasks.json")) as handle:
                self.task_data = json.load(handle)
        if self.parser_data is None:
            with open(resource_path("parser.json")) as handle:
                self.parser_data = json.load(handle)

    def test_task_data(self):
        """
        Makes sure, that the provided task data is in expected structure.
        """
        for data_set in self.task_data:
            self.assertIs(
                type(data_set),
                dict,
            )
            for main_key in [
                "name",
                "description",
                "target_progress",
                "progress_softupdate",
                "expected_recurring_steps",
            ]:
                self.assertIn(
                    main_key,
                    data_set.keys(),
                )

    def test_parser_data(self):
        """
        Makes sure, that the provided parser data is in expected structure.
        """
        for data_set in self.parser_data:
            self.assertIs(type(data_set), dict)
            for main_key in ["tasks", "action", "parameters"]:
                self.assertIn(main_key, data_set.keys())
            tasks = data_set["tasks"]
            self.assertIs(type(tasks), list)
            for task in tasks:
                self.assertIs(type(task), str)
            action = data_set["action"]
            self.assertIs(type(action), str)
            parameters = data_set["parameters"]
            self.assertIs(type(parameters), dict)
            for parameter_key in ["message_template", "pattern", "recurring",
                                  "expected_hits"]:
                self.assertIn(parameter_key, parameters)
            message_template = parameters["message_template"]
            self.assertIs(type(message_template), str)
            pattern = parameters["pattern"]
            self.assertIs(type(pattern), str)
            recurring = parameters["recurring"]
            self.assertIs(type(recurring), bool)
            expected_hits = parameters["expected_hits"]
            self.assertIs(type(expected_hits), int)
            self.assertGreaterEqual(expected_hits, 1)

    def test_consistency(self):
        """
        Assuming the structure of the data is correct, test for consistency in
        given data.
        """
        task_names = [task["name"] for task in self.task_data]
        for parser in self.parser_data:
            for task_name in parser["tasks"]:
                self.assertIn(task_name, task_names)
        progress_steps = [task["target_progress"] for task in self.task_data]
        progress_steps_update = [task["progress_softupdate"] for task in
                                 self.task_data]
        self.assertEqual(progress_steps, sorted(progress_steps))
        self.assertEqual(progress_steps_update, sorted(progress_steps_update))


class TestLineParser(TestCase):
    message = "Test-Message"
    message_template = "Test-Message: {test}"
    simple_regex = "^.+$"
    template_regex = "^(?P<test>.+)$"
    simple_line = "Working in normal parameters."

    def setUp(self):
        self.call_back = FaiProgressMockup()

    def test_plain(self):
        basic_line_parser = LineParser(
            self.call_back.update_progress,
            self.message,
            self.simple_regex,
            recurring=False,
        )
        basic_line_parser.process(self.simple_line)
        self.assertEqual(self.call_back.message, self.message)

    def test_regexp(self):
        basic_line_parser = LineParser(
            self.call_back.update_progress,
            self.message_template,
            self.template_regex,
            recurring=False,
        )
        basic_line_parser.process(self.simple_line)
        self.assertEqual(
            self.call_back.message,
            self.message_template.format(test=self.simple_line),
        )

    def test_message_template_keyword_not_in_regexp(self):
        self.assertRaises(
            KeyError,
            LineParser,
            self.call_back.update_progress,
            self.message_template,
            self.simple_regex,
            recurring=False,
        )


class TestFaiTaskInterface(TestCase):

    def setUp(self):
        self.expected_recurring_steps = 50
        self.task = FaiTask("mock", "Test case", 12.3, None,
                            self.expected_recurring_steps)

    def test_task_step_counter(self):
        progress = 0
        self.assertEqual(self.task.get_progress(), progress)
        for step in range(1, self.expected_recurring_steps):
            self.task.update_progress("Step {i}".format(i=step))
            self.assertEqual(step, self.task.steps)
            new_progress = self.task.get_progress()
            if new_progress < 1:
                self.assertGreater(new_progress, progress)

    def test_expected_steps(self):
        self.assertEqual(
            self.task.expected_steps,
            self.expected_recurring_steps,
        )
        task = FaiTask("mock0", "Test case", 1)
        self.assertEqual(task.expected_steps, 0)
        self.assertEqual(task.get_progress(), 1)

    def test_task_progress_overshoot(self):
        for step in range(60):
            self.task.update_progress("Step {i}".format(i=step))
        self.assertLessEqual(self.task.get_progress(), 1)

    def test_parser_interaction(self):
        message = "waiting for better manners at lkml"
        mock = FaiProgressMockup()
        task = FaiTask("test", "test task", 12.3, None, 0)
        parser = LineParser(task.update_progress, message, ".*", False, 1)
        task.subscribe(mock)
        parser.process("some line")
        self.assertEqual(mock.message, message)
        self.assertEqual(task.steps, 1)
        self.assertEqual(task.get_progress(), 1)
