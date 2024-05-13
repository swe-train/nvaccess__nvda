# A part of NonVisual Desktop Access (NVDA)
# This file is covered by the GNU General Public License.
# See the file COPYING for more details.
# Copyright (C) 2023 NV Access Limited

"""
High-level UIA remote ops Unit tests for writing iterable functions that can yield values.
"""

from unittest import TestCase
from unittest.mock import Mock
from ctypes import POINTER
from UIAHandler import UIA
from UIAHandler._remoteOps import operation
from UIAHandler._remoteOps import remoteAPI
from UIAHandler._remoteOps.lowLevel import (
	PropertyId,
)


class Test_iterable(TestCase):

	def test_iterableFunction(self):
		op = operation.Operation(localMode=True)

		@op.buildIterableFunction
		def code(ra: remoteAPI.RemoteAPI):
			i = ra.newInt(0)
			with ra.whileBlock(lambda: i < 4):
				ra.Yield(i)
				i += 1

		results = []
		for i in op.iterExecute():
			results.append(i)
		self.assertEqual(results, [0, 1, 2, 3])

	def test_long_iterableFunction(self):
		op = operation.Operation(localMode=True)

		@op.buildIterableFunction
		def code(ra: remoteAPI.RemoteAPI):
			executionCount = ra.newInt(0, static=True)
			executionCount += 1
			i = ra.newInt(0, static=True)
			j = ra.newInt(0, static=True)
			with ra.whileBlock(lambda: i < 5000):
				with ra.ifBlock(j == 1000):
					ra.Yield(i)
					j.set(0)
				i += 1
				j += 1
			ra.Yield(executionCount)

		results = []
		for i in op.iterExecute(maxTries=20):
			results.append(i)
		self.assertEqual(results[:-1], list(range(1000, 5000, 1000)))
		self.assertEqual(results[-1], 4)

	def test_forEachNumInRange(self):
		op = operation.Operation(localMode=True)

		@op.buildIterableFunction
		def code(ra: remoteAPI.RemoteAPI):
			with ra.forEachNumInRange(10, 15) as i:
				ra.Yield(i)

		results = []
		for i in op.iterExecute():
			results.append(i)
		self.assertEqual(results, [10, 11, 12, 13, 14])

	def test_forEachItemInArray(self):
		op = operation.Operation(localMode=True)

		@op.buildIterableFunction
		def code(ra: remoteAPI.RemoteAPI):
			array = ra.newArray()
			with ra.forEachNumInRange(0, 10, 2) as i:
				array.append(i)
			with ra.forEachItemInArray(array) as item:
				ra.Yield(item)

		results = []
		for i in op.iterExecute():
			results.append(i)
		self.assertEqual(results, [0, 2, 4, 6, 8])
