# -*- coding: utf-8; -*-
#
# Copyright (C) 2014-2015  DING Changchang
#
# This file is part of Avalon Management System (AMS).
#
# AMS is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# AMS is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with AMS. If not, see <http://www.gnu.org/licenses/>.

import threading
import logging
import time

import mysql.connector


class SQLThread(threading.Thread):
    def __init__(self, sql_queue, host, database, user, password, single):
        threading.Thread.__init__(self)
        self.sql_queue = sql_queue
        self.host = host
        self.database = database
        self.user = user
        self.password = password
        self.log = logging.getLogger('AMS.SQLThread')
        self.single = single

    def run(self):
        retry = 0
        while retry < 3:
            try:
                conn = mysql.connector.connect(
                    host=self.host,
                    user=self.user,
                    password=self.password,
                    database=self.database
                )
                break
            except mysql.connector.Error:
                time.sleep(2)
                retry += 1

        if retry == 3:
            return

        cursor = conn.cursor()
        sql = SQL(cursor)

        while True:
            sql_raw = self.sql_queue.get()
            if sql_raw == "end":
                if not self.single:
                    self.sql_queue.put("end")
                break
            sql.run(**sql_raw)
            conn.commit()

        cursor.close()
        conn.close()


class SQL():
    def __init__(self, cursor):
        self.cursor = cursor
        self.log = logging.getLogger('AMS.SQL')

    def _create(self, name, column_def, additional=None, suffix=None):
        self.query = 'CREATE TABLE IF NOT EXISTS `{}` ({}{}) {}'.format(
            name,
            ', '.join('`{name}` {type}'.format(**c) for c in column_def),
            ', {}'.format(additional) if additional else '',
            suffix if suffix else ''
        )
        self.value = None

    def _insert(self, name, column, value):
        self.query = 'INSERT INTO `{}` (`{}`) VALUES ({})'.format(
            name,
            '`, `'.join(column),
            ', '.join('%s' for i in range(len(value)))
        )
        self.value = value

    def _select(self, name, column, clause):
        self.query = 'SELECT `{}` FROM `{}` WHRER {}'.format(
            '`, `'.join(column),
            name,
            clause
        )
        self.value = None

    def _raw(self, query, value=None):
        self.query = query
        self.value = value

    def run(self, command, *args, **kwargs):
        if command == 'create':
            self._create(*args, **kwargs)
        elif command == 'insert':
            self._insert(*args, **kwargs)
        elif command == 'select':
            self._select(*args, **kwargs)
        elif command == 'raw':
            self._raw(*args, **kwargs)
        else:
            self.log.error('Unknown sql command: {}'.format(command))
            return False

        try:
            self.cursor.execute(self.query, self.value)
            return True
        except mysql.connector.Error as e:
            self.log.error(str(e))
            self.log.debug(self.query)
            if self.value is not None:
                self.log.debug(self.value)
            return False


def sql_handler(sql_queue, db):

    t = SQLThread(
        sql_queue[0],
        db['host'],
        db['database'],
        db['user'],
        db['password'],
        single=True
    )
    t.start()
    t.join()

    threads = []
    for i in range(db['thread_num']):
        t = SQLThread(
            sql_queue[1],
            db['host'],
            db['database'],
            db['user'],
            db['password'],
            single=False
        )
        t.start()
        threads.append(t)

    for t in threads:
        t.join()

    t = SQLThread(
        sql_queue[0],
        db['host'],
        db['database'],
        db['user'],
        db['password'],
        single=True
    )
    t.start()
    t.join()