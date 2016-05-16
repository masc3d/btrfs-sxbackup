# Copyright (c) 2014 Marco Schindler
#
# This program is free software; you can redistribute it and/or modify it
# under the terms of the GNU General Public License as published by the Free
# Software Foundation; either version 2 of the License, or (at your option)
# any later version.

import collections
import logging
import math
import re
from datetime import datetime
from datetime import timedelta
from datetime import timezone


def _splice(items_to_splice, lambda_condition):
    """
    Splice items matching a condition
    :param items_to_splice: Items to splice
    :param lambda_condition: Condition to match
    :return: (remainder, matched) tuple of lists
    """
    remainder = list()
    spliced = list()
    for item in items_to_splice:
        if lambda_condition(item):
            spliced.append(item)
        else:
            remainder.append(item)
    return remainder, spliced


class RetentionExpression:
    """
    Represents a sequence of conditions describing which backups to retain.
    Each regular condition is defined as <age>:<ratio>

    Age is defined as: <amount><time span literal> where time span is one of h, d, w or m (hours, days, weeks or months)
    Examples for age: 6h, 4d, 1w, 2m

    Ratio is defined as: <amount>/<time span literal> where time span is one of h, d, w or m (hours, days, weeks, or
    months)
    Examples for ratio: 1/d, 3/w, 10/m (read 1 per day, 3 per week, 10 per month)

    Example for a full keep expression: 1d:4/d, 1w:1/d, 1m:1/w, 2m:none
    Translating to: after 1 day, keep 4 per day, after 1 week keep one per day, after 1 month keep 1 per week, after 2
    months keep none

    Special cases:
    * A ratio can be a static numbers, defining a static number of backups without timespan
    * An entire condition can be a static number, defining a static number of backups without timespan and age
    """

    class Condition:
        """
        Each condition of a retention expression reflects how many backups to retain after a specific amount of time
        """

        __kd = {'h': timedelta(hours=1),
                'd': timedelta(days=1),
                'w': timedelta(days=7),
                'm': timedelta(days=30),
                'y': timedelta(days=365),
                'n': None}

        __retain_re = re.compile('^([0-9]+)(/([0-9]+)?([hdwmy]))?$', re.IGNORECASE)
        __age_re = re.compile('^([0-9]+)([hdwmy])?$', re.IGNORECASE)

        def __init__(self, age: timedelta, interval_duration: timedelta, interval_amount: int, text: str):
            self.__text = text
            self.__age = age
            self.__interval_duration = interval_duration
            self.__interval_amount = interval_amount

        @staticmethod
        def parse(text):
            # Parse criteria expression
            c_parts = text.split(':')
            if len(c_parts) != 2:
                try:
                    age = timedelta(0)
                    interval_duration = None
                    interval_amount = int(text)
                except:
                    raise ValueError('Criteria must consist of age and interval separated by colon [%s]'
                                     % text)
            else:
                age_literal = c_parts[0].strip()
                retain_literal = c_parts[1].strip()

                # Parse age (examples: 4d, 4w, 30 ..)
                match = RetentionExpression.Condition.__age_re.match(age_literal)
                if match is None:
                    raise ValueError('Invalid age [%s]' % age_literal)

                if match.group(2) is not None:
                    # Time literal part of age
                    age = int(match.group(1)) * RetentionExpression.Condition.__kd[match.group(2)]
                else:
                    # Plain number of hours
                    age = timedelta(hours=int(match.group(1)))

                # Parse keep expression (examples: 4/d, 4/w, 20 ..)
                if retain_literal[0] in RetentionExpression.Condition.__kd:
                    interval_duration = RetentionExpression.Condition.__kd[retain_literal[0]]
                    interval_amount = 1 if interval_duration is not None else 0
                else:
                    match = RetentionExpression.Condition.__retain_re.match(retain_literal)
                    if match is None:
                        raise ValueError('Invalid retention [%s]' % retain_literal)
                    interval_amount = int(match.group(1))

                    if match.group(3) is None and match.group(4) is None:
                        interval_duration = None
                    else:
                        if match.group(3) is not None:
                            interval_mult = int(match.group(3))
                        else:
                            interval_mult = 1

                        interval_duration = interval_mult * RetentionExpression.Condition.__kd[str(match.group(4)[0])]

            return RetentionExpression.Condition(age=age,
                                                 interval_duration=interval_duration,
                                                 interval_amount=interval_amount,
                                                 text=text)

        @property
        def text(self):
            return self.__text

        @property
        def age(self):
            return self.__age

        @property
        def interval_duration(self):
            return self.__interval_duration

        @property
        def interval_amount(self):
            return self.__interval_amount

        def __repr__(self):
            return 'Condition(age=%s, retain_amount=%s, retain_interval=%s)' \
                   % (self.age, self.interval_amount, self.interval_duration)

        def __str__(self):
            return self.text

    class ApplicableInterval:
        """
        Applicable interval, relative to a timestamp
        """

        def __init__(self, start, duration, amount):
            self.__start = start
            self.__duration = duration
            self.__amount = amount
            self.__end = self.__start - self.__duration if self.__duration is not None else None

        @property
        def start(self):
            return self.__start

        @property
        def duration(self):
            return self.__duration

        @property
        def amount(self):
            return self.__amount

        @property
        def end(self):
            return self.__end

        def __repr__(self):
            return 'ApplicableInterval(start=%s, duration=%s, amount=%s, end=%s)' \
                   % (self.start, self.duration, self.amount, self.end)

        @staticmethod
        def __reduce(items, max_amount):
            """
            Reduces a list of items evenly
            :param items: List of items to reduce
            :param max_amount: Maximum amount of items to retain
            :return: (to_retain, to_remove) tuple of lists
            """
            to_retain = list()
            to_remove = list()

            if max_amount == 0:
                return list(), list(items)

            if len(items) > max_amount:
                s = len(items) / (max_amount + 1) - 1
                ss = len(items) / max_amount
                next_index = round(s)
                for j in range(0, len(items)):
                    item = items[j]
                    if j == next_index:
                        to_retain.append(item)
                        s += ss
                        next_index = round(s)
                    else:
                        to_remove.append(item)
            else:
                to_retain.extend(items)

            return to_retain, to_remove

        def filter(self, items, lambda_timestamp):
            """
            Filters item according to criteria defined by this interval
            :param items: Items to filter
            :param lambda_timestamp: Lambda to return timestamp for each item
            :return: (items, to_retain, to_remove) The items which have not matched and one list items to retain/remove
            """
            if self.end is not None:
                (items, interval_items) = _splice(items, lambda i: self.start >= lambda_timestamp(i) > self.end)
                # Reverse item list before reducing to avoid a newer item being kept for single item intervals
                # on every iteration (run) which would effectively break retention, as items within those
                # intervals would never age
                (to_retain, to_remove) = self.__reduce(list(reversed(interval_items)), self.amount)
            else:
                to_retain = items[:self.amount]
                to_remove = items[self.amount:]
                items = list()

            return items, to_retain, to_remove

    class ApplicableCondition(Condition):
        """
        Applicable condition, relative to a timestamp
        """

        def __init__(self, condition, initial_time, end_time):
            super().__init__(age=condition.age,
                             interval_duration=condition.interval_duration,
                             interval_amount=condition.interval_amount,
                             text=condition.text)
            self.__condition = condition
            self.__initial_time = initial_time
            self.__start_time = initial_time - condition.age
            self.__end_time = end_time

            # Calculate interval duration using next condition if needed
            interval_duration = condition.interval_duration
            if interval_duration is None:
                # If keep interval is not defined (static number of items)
                # calculate the interval -> difference to subsequent condition
                if self.__end_time is not None:
                    interval_duration = self.__start_time - self.__end_time

            self.__interval_duration = interval_duration

            self.__end_time = end_time

        @property
        def initial_time(self):
            return self.__initial_time

        @property
        def start_time(self):
            return self.__start_time

        @property
        def end_time(self):
            return self.__end_time

        def __repr__(self):
            return 'ApplicableCondition(condition=%s, initial_time=%s, start_time=%s, end_time=%s)' \
                   % (repr(self.__condition), self.initial_time, self.start_time, self.end_time)

        def create_interval_by_timestamp(self, timestamp):
            """
            Creates an appropriate applicable interval within this condition timeframe
            :param timestamp: Timestamp
            :return: ApplicableInterval or None if timestamp out of bounds of the condition start/end time
            """
            if timestamp > self.start_time or \
                    (self.end_time is not None and timestamp <= self.end_time):
                return None

            if self.__interval_duration is None:
                return RetentionExpression.ApplicableInterval(self.start_time,
                                                              self.interval_duration,
                                                              self.interval_amount)

            # Calculate interval factor
            f = math.floor((self.start_time - timestamp) / self.interval_duration)

            return RetentionExpression.ApplicableInterval(self.start_time - f * self.interval_duration,
                                                          self.interval_duration,
                                                          self.interval_amount)

    def __create_applicable_conditions(self, initial_time):
        """
        Create applicable conditions from this retention expression
        :param initial_time: Start time for conditions
        :return: List of applicable conditions
        """
        return list(map(lambda i:
                        RetentionExpression.ApplicableCondition(
                            condition=self.__conditions[i],
                            initial_time=initial_time,
                            # End time is the start time of the next condition or None if it's the last
                            end_time=(initial_time - self.__conditions[i + 1].age)
                            if i < len(self.__conditions) - 1
                            else None),
                    range(0, len(self.__conditions))))

    def __init__(self, expression):
        """
        c'tor
        :param expression: Expression string defining multiple criteria for retaining backups
        """
        self.__logger = logging.getLogger(self.__class__.__name__)
        expression = str(expression)

        # Parse keep expression string
        # Split criteria list
        criteria = expression.split(',')

        # Strip criteria of whitespaces and reformat expression text
        criteria = list(map(lambda x: x.strip(), criteria))
        self.__expression_text = ', '.join(criteria)

        # Iterate and parse
        conditions = list(map(lambda x: RetentionExpression.Condition.parse(x), criteria))

        # Conditions sorted by age
        self.__conditions = sorted(conditions, key=lambda c: c.age)

    def __str__(self):
        return self.__expression_text

    @property
    def expression_text(self):
        return self.__expression_text

    def filter(self, items: list, lambda_timestamp):
        """
        Filter items according to retention expression
        :param items: Items to filter
        :param lambda_timestamp: Lambda to return the timestamp for each item
        :return: (items_to_remove_by_condition, items_to_retain)
        """

        if len(self.__conditions) == 0:
            return list(), list(items)

        if len(items) == 0:
            return list(), list()

        items = sorted(items, key=lambda_timestamp, reverse=True)

        items_to_retain = list()
        items_to_remove_by_condition = collections.OrderedDict()

        now = datetime.now(timezone.utc)
        conditions = self.__create_applicable_conditions(now)

        # Splice recent items (newer than first condition age)
        (items, recent_items) = _splice(items, lambda i: lambda_timestamp(i) > (now - self.__conditions[0].age))
        items_to_retain.extend(recent_items)

        while len(items) > 0 and len(conditions) > 0:
            item_timestamp = lambda_timestamp(items[0])
            condition = conditions[0]

            # Get interval for current condition
            interval = condition.create_interval_by_timestamp(item_timestamp)
            if interval is None:
                # Condition out of range, try next one
                conditions.pop(0)
                continue

            items_to_remove = list()

            (items, to_retain, to_remove) = interval.filter(items, lambda_timestamp)
            items_to_retain.extend(to_retain)
            items_to_remove.extend(to_remove)

            if len(items_to_remove) > 0:
                if condition not in items_to_remove_by_condition:
                    items_to_remove_by_condition[condition] = items_to_remove
                else:
                    items_to_remove_by_condition[condition].extend(items_to_remove)

        return items_to_remove_by_condition, items_to_retain
