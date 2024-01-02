# A part of NonVisual Desktop Access (NVDA)
# This file is covered by the GNU General Public License.
# See the file COPYING for more details.
# Copyright (C) 2023-2023 NV Access Limited

import enum
import functools
from numbers import Number
from typing import Optional, Self, Union, Callable
import contextlib
import _ctypes
import ctypes
from ctypes import (
	_SimpleCData,
	c_long,
	c_ulong,
	c_ushort,
	c_byte,
	c_char,
	c_wchar,
	c_bool
)
from comtypes import GUID
from dataclasses import dataclass
import inspect
import os
import struct
import itertools
from UIAHandler import UIA
from . import lowLevel
from logHandler import log


class RelativeOffset(c_long):
	def __repr__(self) -> str:
		return f"RelativeOffset {self.value}"


class OperandId(c_long):
	def __repr__(self) -> str:
		return f"OperandId {self.value}"


def _getLocationString(frame: inspect.FrameInfo) -> str:
	"""
	Returns a string describing the location of the given frame.
	It includes all ancestor frames with the same file path,
	plus one more frame with a different file path,
	so you can see what called into the file.
	"""
	locations = []
	oldPath = None
	while frame:
		path = os.path.relpath(inspect.getfile(frame))
		locations.append(
			f"File \"{path}\", line {frame.f_lineno}, in {frame.f_code.co_name}"
		)
		if oldPath and path != oldPath:
			break
		oldPath = path
		frame = frame.f_back
	locationString = "\n".join(reversed(locations))
	return locationString


@dataclass
class _InstructionRecord:
	instructionType: lowLevel.InstructionType
	params: list[bytes]
	locationString: str

	def __repr__(self):
		return f"{self.instructionType.name}({', '.join(map(repr, self.params))})\n{self.locationString}"


class _RemoteBaseObject:
	""" A base class for all remote objects. """

	_isTypeInstruction: lowLevel.InstructionType

	@classmethod
	def _new(cls, rob: "RemoteOperationBuilder", initialValue: object=None) -> "_RemoteBaseObject":
		operandId = rob._getNewOperandId()
		cls._initOperand(rob, operandId, initialValue)
		return cls(rob, operandId)

	@classmethod
	def _initOperand(cls, operandId: int, initialValue: object):
		raise NotImplementedError()

	def __init__(self, rob: "RemoteOperationBuilder", operandId: int):
		self._rob = rob
		self._operandId = operandId

	def __repr__(self) -> str:
		return f"{self.__class__.__name__} at {self.operandId}"

	@property
	def operandId(self) -> OperandId:
		return self._operandId

	def set(self, value: object) -> None:
		value = self._rob._ensureRemoteObject(value, useCache=True)
		self._rob._addInstruction(
			lowLevel.InstructionType.Set,
			self.operandId,
			value.operandId
		)

	def stringify(self) -> "RemoteString":
		resultOperandId = self._rob._getNewOperandId() 
		result = RemoteString(self._rob, resultOperandId)
		self._rob._addInstruction(
			lowLevel.InstructionType.Stringify,
			resultOperandId,
			self.operandId
		)
		return result

	def _doCompare(self, comparisonType: lowLevel.ComparisonType, other: Self | object) -> bool:
		other = self._rob._ensureRemoteObject(other, useCache=True)
		resultOperandId = self._rob._getNewOperandId()
		result = RemoteBool(self._rob, resultOperandId)
		self._rob._addInstruction(
			lowLevel.InstructionType.Compare,
			result.operandId,
			self.operandId,
			other.operandId,
			c_long(comparisonType)
		)
		return result


class _RemoteEqualityComparible(_RemoteBaseObject):

	def __eq__(self, other: object) -> bool:
		return self._doCompare(lowLevel.ComparisonType.Equal, other)

	def __ne__(self, other: object) -> bool:
		return self._doCompare(lowLevel.ComparisonType.NotEqual, other)

class _RemoteIntegral(_RemoteBaseObject):
	_newInstruction: lowLevel.InstructionType
	_initialValueType = _SimpleCData

	@classmethod
	def _initOperand(cls, rob: "RemoteOperationBuilder", operandId: int, initialValue: object):
		rob._addInstruction(
			cls._newInstruction,
			operandId,
			cls._initialValueType(initialValue)
		)


class _RemoteNumber(_RemoteIntegral):

	def __gt__(self, other: Self | Number) -> bool:
		return self._doCompare(lowLevel.ComparisonType.GreaterThan, other)

	def __lt__(self, other: Self | Number) -> bool:
		return self._doCompare(lowLevel.ComparisonType.LessThan, other)

	def __ge__(self, other: Self | Number) -> bool:
		return self._doCompare(lowLevel.ComparisonType.GreaterThanOrEqual, other)

	def __le__(self, other: Self | Number) -> bool:
		return self._doCompare(lowLevel.ComparisonType.LessThanOrEqual, other)

	def _doBinaryOp(self, instructionType: lowLevel.InstructionType, other: Self | Number) -> Self:
		other = self._rob._ensureRemoteObject(other, useCache=True)
		resultOperandId = self._rob._getNewOperandId()
		result = type(self)(self._rob, resultOperandId)
		self._rob._addInstruction(
			instructionType,
			result.operandId,
			self.operandId,
			other.operandId
		)
		return result

	def _doInplaceOp(self, instructionType: lowLevel.InstructionType, other: Self | Number) -> Self:
		other = self._rob._ensureRemoteObject(other, useCache=True)
		self._rob._addInstruction(
			instructionType,
			self.operandId,
			other.operandId
		)
		return self

	def __add__(self, other: Self | Number) -> Self:
		return self._doBinaryOp(lowLevel.InstructionType.BinaryAdd, other)

	def __iadd__(self, other: Self | Number) -> Self:
		return self._doInplaceOp(lowLevel.InstructionType.Add, other)

	def __sub__(self, other: Self | Number) -> Self:
		return self._doBinaryOp(lowLevel.InstructionType.BinarySubtract, other)

	def __isub__(self, other: Self | Number) -> Self:
		return self._doInplaceOp(lowLevel.InstructionType.Subtract, other)

	def __mul__(self, other: Self | Number) -> Self:
		return self._doBinaryOp(lowLevel.InstructionType.BinaryMultiply, other)

	def __imul__(self, other: Self | Number) -> Self:
		return self._doInplaceOp(lowLevel.InstructionType.Multiply, other)

	def __truediv__(self, other: Self | Number) -> Self:
		return self._doBinaryOp(lowLevel.InstructionType.BinaryDivide, other)

	def __itruediv__(self, other: Self | Number) -> Self:
		return self._doInplaceOp(lowLevel.InstructionType.Divide, other)


class RemoteInt(_RemoteNumber):
	_isTypeInstruction = lowLevel.InstructionType.IsInt
	_newInstruction = lowLevel.InstructionType.NewInt
	_initialValueType = c_long


class RemoteBool(_RemoteIntegral):
	_isTypeInstruction = lowLevel.InstructionType.IsBool
	_newInstruction = lowLevel.InstructionType.NewBool
	_initialValueType = c_bool


class RemoteString(_RemoteEqualityComparible):
	_isTypeInstruction = lowLevel.InstructionType.IsString

	@classmethod
	def _initOperand(cls, rob: "RemoteOperationBuilder", operandId: int, initialValue: str):
		rob._addInstruction(
			lowLevel.InstructionType.NewString,
			operandId,
			ctypes.create_unicode_buffer(initialValue)
		)

	def _concat(self, other, toResult) -> None:
		if not isinstance(toResult, RemoteString):
			raise TypeError("toResult must be a RemoteString")
		if not isinstance(other, RemoteString):
			if isinstance(other, str):
				other = self._rob._ensureRemoteObject(other, useCache=True)
			elif isinstance(other, _RemoteBaseObject):
				other = other.stringify()
			else:
				raise TypeError("other must be a RemoteString, a str, or a _RemoteBaseObject")
		self._rob._addInstruction(
			lowLevel.InstructionType.RemoteStringConcat ,
			toResult.operandId,
			self.operandId,
			other.operandId
		)

	def __add__(self, other: Self | _RemoteBaseObject | str) -> Self:
		resultOperandId = self._rob._getNewOperandId()
		result = RemoteString(self._rob, resultOperandId)
		self._concat(other, result)
		return result

	def __iadd__(self, other: Self | _RemoteBaseObject | str) -> Self:
		self._concat(other, self)
		return self


class _RemoteNullable(_RemoteBaseObject):

	@classmethod
	def _initOperand(cls, rob: "RemoteOperationBuilder", operandId: int, initialValue: None=None):
		rob._addInstruction(
			lowLevel.InstructionType.NewNull,
			operandId,
		)

	def isNull(self) -> bool:
		result = RemoteBool._new(self._rob, False)
		self._rob._addInstruction(
			lowLevel.InstructionType.IsNull,
			result.operandId,
			self.operandId
		)
		return result


class RemoteVariant(_RemoteNullable):

	def isType(self, remoteClass: type[_RemoteBaseObject]) -> bool:
		if not issubclass(remoteClass, _RemoteBaseObject):
			raise TypeError("remoteClass must be a subclass of _RemoteBaseObject")
		result = self._rob.newBool()
		self._rob._addInstruction(
			remoteClass._isTypeInstruction,
			result.operandId,
			self.operandId
		)
		return result

	def asType(self, remoteClass: type[_RemoteBaseObject]) -> _RemoteBaseObject:
		return remoteClass(self._rob, self.operandId)


class RemoteExtensionTarget(_RemoteNullable):

	def isExtensionSupported(self, extensionGuid: GUID) -> bool:
		extensionGuid = self._rob._ensureRemoteObject(extensionGuid, useCache=True)
		resultOperandId = self._rob._getNewOperandId()
		result = RemoteBool(self._rob, resultOperandId)
		self._rob._addInstruction(
			lowLevel.InstructionType.IsExtensionSupported,
			result.operandId,
			self.operandId,
			extensionGuid.operandId
		)
		return result

	def callExtension(self, extensionGuid: GUID, *params: _RemoteBaseObject) -> None:
		extensionGuid = self._rob._ensureRemoteObject(extensionGuid, useCache=True)
		self._rob._addInstruction(
			lowLevel.InstructionType.CallExtension,
			self.operandId,
			extensionGuid.operandId,
			c_long(len(params)),
			*(p.operandId for p in params)
		)


class RemoteElement(RemoteExtensionTarget):
	_isTypeInstruction = lowLevel.InstructionType.IsElement

	def getPropertyValue(self, propertyId: int, ignoreDefault: bool=False) -> object:
		propertyId = self._rob._ensureRemoteObject(propertyId, useCache=True)
		if not isinstance(ignoreDefault, RemoteBool):
			ignoreDefault = self._rob._ensureRemoteObject(ignoreDefault, useCache=True)
		resultOperandId = self._rob._getNewOperandId()
		result = RemoteVariant(self._rob, resultOperandId)
		self._rob._addInstruction(
			lowLevel.InstructionType.GetPropertyValue,
			result.operandId,
			self.operandId,
			propertyId.operandId,
			ignoreDefault.operandId
		)
		return result


class RemoteTextRange(RemoteExtensionTarget):
	pass


class RemoteGuid(_RemoteEqualityComparible):
	_isTypeInstruction = lowLevel.InstructionType.IsGuid

	@classmethod
	def _initOperand(cls, rob: "RemoteOperationBuilder", operandId: int, initialValue: Union[GUID, str]):
		if isinstance(initialValue, str):
			initialValue = GUID(initialValue)
		rob._addInstruction(
			lowLevel.InstructionType.NewGuid,
			operandId,
			initialValue
		)


class MalformedBytecodeException(RuntimeError):
	pass


class InstructionLimitExceededException(RuntimeError):
	pass


class RemoteException(RuntimeError):
	pass


class ExecutionFailureException(RuntimeError):
	pass


class RemoteOperationBuilder:

	_versionBytes = struct.pack('l', 0) 

	_pyClassToRemoteClass = {
		int: RemoteInt,
		bool: RemoteBool,
		str: RemoteString,
		GUID: RemoteGuid,
	}

	def __init__(self, enableLogging: bool=False):
		self._scopeJustExited: _RemoteScope | None = None
		self._instructions: list[_InstructionRecord] = []
		self._lastIfConditionInstructionPendingElse: _InstructionRecord | None = None
		self.operandIdGen = itertools.count(start=1)
		self._remotedObjectCache: dict[object, _RemoteBaseObject] = {}
		self._ro = lowLevel.RemoteOperation()
		self._results = None
		self._loggingEnablede = enableLogging
		if enableLogging:
			self._log: RemoteString = self.newString()
			self.addToResults(self._log)

	def _getNewOperandId(self) -> OperandId | RelativeOffset:
		return OperandId(next(self.operandIdGen))

	def _addInstruction(self, instruction: lowLevel.InstructionType, *params: Union[_SimpleCData, ctypes.Array, _RemoteBaseObject]):
		""" Adds an instruction to the instruction list and returns the index of the instruction. """
		""" Adds an instruction to the instruction list and returns the index of the instruction. """
		self._scopeJustExited = None
		frame = inspect.currentframe().f_back
		locationString = _getLocationString(frame)
		self._instructions.append(
			_InstructionRecord(instruction, params, locationString)
		)
		return len(self._instructions) - 1

	def _generateByteCode(self) -> bytes:
		byteCode = b''
		for instruction in self._instructions:
			byteCode += struct.pack('l', instruction.instructionType)
			for param in instruction.params:
				print(f"param: {param}")
				paramBytes = (c_char*ctypes.sizeof(param)).from_address(ctypes.addressof(param)).raw
				if isinstance(param, _ctypes.Array) and param._type_ == c_wchar:
					paramBytes = paramBytes[:-2]
					byteCode += struct.pack('l', len(param) - 1)
				byteCode += paramBytes
		return byteCode

	def importElement(self, element: UIA.IUIAutomationElement) -> RemoteElement:
		operandId = self._getNewOperandId()
		self._ro.importElement(operandId, element)
		return RemoteElement(self, operandId)

	def importTextRange(self, textRange: UIA.IUIAutomationTextRange):
		operandId = self._getNewOperandId()
		self._ro.importTextRange(operandId, textRange)
		return RemoteTextRange(self, operandId)

	@property
	def _lastInstructionIndex(self):
		return len(self._instructions) - 1

	def _getInstructionRecord(self, instructionIndex: int) -> _InstructionRecord:
		return self._instructions[instructionIndex]

	def newInt(self, initialValue: int=0) -> RemoteInt:
		return RemoteInt._new(self, initialValue)

	def newBool(self, initialValue: bool=False) -> RemoteBool:
		return RemoteBool._new(self, initialValue)

	def newString(self, initialValue: str="") -> RemoteString:
		return RemoteString._new(self, initialValue)

	def newVariant(self) -> RemoteVariant:
		return RemoteVariant._new(self)

	def newNULLExtensionTarget(self) -> RemoteExtensionTarget:
		return RemoteExtensionTarget._new(self)

	def newNULLElement(self) -> RemoteElement:
		return RemoteElement._new(self)

	def newNULLTextRange(self) -> RemoteTextRange:
		return RemoteTextRange._new(self)

	def newGuid(self, initialValue: GUID) -> RemoteGuid:
		return RemoteGuid._new(self, initialValue)

	def ifBlock(self, condition: RemoteBool):
		return _RemoteIfBlockBuilder(self, condition)

	def elseBlock(self):
		return _RemoteElseBlockBuilder(self)

	def whileBlock(self, conditionBuilderFunc: Callable[[], RemoteBool]):
		return _RemoteWhileBlockBuilder(self, conditionBuilderFunc)

	def breakLoop(self):
		self._addInstruction(lowLevel.InstructionType.BreakLoop)

	def continueLoop(self):
		self._addInstruction(lowLevel.InstructionType.ContinueLoop)

	def tryBlock(self):
		return _RemoteTryBlockBuilder(self)

	def catchBlock(self):
		return _RemoteCatchBlockBuilder(self)

	def setOperationStatus(self, status: int | RemoteInt):
			status = self._ensureRemoteObject(status, useCache=True)
			self._addInstruction(
				lowLevel.InstructionType.SetOperationStatus,
				status.operandId
			)

	def getOperationStatus(self) -> RemoteInt:
		resultOperandId = self._getNewOperandId()
		self._addInstruction(
			lowLevel.InstructionType.GetOperationStatus,
			resultOperandId
		)
		return RemoteInt(self, resultOperandId)

	def halt(self):
		self._addInstruction(lowLevel.InstructionType.Halt)

	def logMessage(self,*strings): 
		if not self._loggingEnablede:
			return
		for string in strings:
			self._log += string
		self._log += "\n"

	def addToResults(self, remoteObj: _RemoteBaseObject):
		self._ro.addToResults(remoteObj.operandId)

	def _ensureRemoteObject(self, obj: object, useCache=False) -> _RemoteBaseObject:
		if isinstance(obj, _RemoteBaseObject):
			return obj
		if isinstance(obj, enum.Enum):
			obj = obj.value
		if useCache:
			cacheKey = (type(obj), obj)
			remoteObj = self._remotedObjectCache.get(obj)
			if remoteObj is not None:
				return remoteObj
		if isinstance(obj, UIA.IUIAutomationElement):
			remoteObj = self.importElement(obj)
		elif isinstance(obj, UIA.IUIAutomationTextRange):
			remoteObj = self.importTextRange(obj)
		else:
			remoteClass = self._pyClassToRemoteClass.get(type(obj))
			if remoteClass:
				remoteObj = remoteClass._new(self, obj)
			else:
				raise TypeError(f"{type(obj)} is not a supported type")
		if useCache:
			self._remotedObjectCache[cacheKey] = remoteObj
		return remoteObj

	def importObjects(self, *imports: object) -> list[_RemoteBaseObject]:
		remoteObjects = []
		for importObj in imports:
			remoteObj = self._ensureRemoteObject(importObj)
			remoteObjects.append(remoteObj)
		return remoteObjects

	def execute(self):
		self.halt()
		byteCode = self._generateByteCode()
		self._results = self._ro.execute(self._versionBytes + byteCode)
		status = self._results.status
		if status == lowLevel.RemoteOperationStatus.MalformedBytecode:
			raise MalformedBytecodeException()
		elif status == lowLevel.RemoteOperationStatus.InstructionLimitExceeded:
			raise InstructionLimitExceededException()
		elif status == lowLevel.RemoteOperationStatus.UnhandledException:
			instructionRecord = self._getInstructionRecord(self._results.errorLocation)
			message = f"\nError at instruction {self._results.errorLocation}: {instructionRecord}\nExtended error: {self._results.extendedError}"
			if self._loggingEnablede:
				try:
					logText = self.dumpLog()
					message += f"\n{logText}"
				except Exception as e:
					message += f"\nFailed to dump log: {e}\n"
			message += self._dumpInstructions()
			raise RemoteException(message)
		elif status == lowLevel.RemoteOperationStatus.ExecutionFailure:
			raise ExecutionFailureException()

	def getResult(self, remoteObj: _RemoteBaseObject) -> object:
		if not self._results:
			raise RuntimeError("Not executed")
		operandId = remoteObj.operandId
		if not self._results.hasOperand(operandId):
			raise LookupError("No such operand")
		return self._results.getOperand(operandId).value

	def dumpLog(self):
		if not self._loggingEnablede:
			raise RuntimeError("Logging not enabled")
		if self._log is None:
			return "Empty remote log"
		output = "--- remote log start ---\n"
		output += self.getResult(self._log)
		output += "--- remote log end ---"
		return output

	def _dumpInstructions(self) -> str:
		output = "--- Instructions start ---\n"
		for index, instruction in enumerate(self._instructions):
			output += f"{index}: {instruction.instructionType.name} {instruction.params}\n"
		output += "--- Instructions end ---"
		return output


class _RemoteScope:

	def __init__(self, rob: RemoteOperationBuilder):
		self._rob = rob

	def __enter__(self):
		self._rob._scopeJustExited = None

	def __exit__(self, exc_type, exc_val, exc_tb):
		self._rob._scopeJustExited = self


class _RemoteIfBlockBuilder(_RemoteScope):

	def __init__(self, remoteOpBuilder: RemoteOperationBuilder, condition: RemoteBool): 
		super().__init__(remoteOpBuilder)
		self._condition = condition

	def __enter__(self):
		super().__enter__()
		self._conditionInstructionIndex = self._rob._addInstruction(
			lowLevel.InstructionType.ForkIfFalse ,
			self._condition.operandId,
			RelativeOffset(1), # offset updated in Else method 
		)

	def __exit__(self, exc_type, exc_val, exc_tb):
		nextInstructionIndex = self._rob._lastInstructionIndex + 1
		relativeJumpOffset = nextInstructionIndex - self._conditionInstructionIndex
		conditionInstruction = self._rob._getInstructionRecord(self._conditionInstructionIndex)
		conditionInstruction.params[1].value = relativeJumpOffset
		super().__exit__(exc_type, exc_val, exc_tb)


class _RemoteElseBlockBuilder(_RemoteScope):

	def __enter__(self):
		if not isinstance(self._rob._scopeJustExited, _RemoteIfBlockBuilder):
			raise RuntimeError("Else block not directly preceded by If block") 
		ifScope = self._rob._scopeJustExited
		super().__enter__()
		conditionInstruction = self._rob._getInstructionRecord(ifScope._conditionInstructionIndex)
		# add a final jump instruction to the previous if block to skip over the else block.
		self._jumpInstructionIndex = self._rob._addInstruction(
			lowLevel.InstructionType.Fork ,
			RelativeOffset(1), # offset updated in __exit__ method 
		)
		# increment the false offset of the previous if block to take the new jump instruction into account. 
		conditionInstruction.params[1].value += 1

	def __exit__(self, exc_type, exc_val, exc_tb):
		# update the jump instruction to jump to the real end of the else block. 
		nextInstructionIndex = self._rob._lastInstructionIndex + 1
		relativeJumpOffset = nextInstructionIndex - self._jumpInstructionIndex
		jumpInstruction = self._rob._getInstructionRecord(self._jumpInstructionIndex)
		jumpInstruction.params[0].value = relativeJumpOffset
		super().__exit__(exc_type, exc_val, exc_tb)


class _RemoteWhileBlockBuilder(_RemoteScope):

	def __init__(self, remoteOpBuilder: RemoteOperationBuilder, conditionBuilderFunc: Callable[[], RemoteBool]):
		super().__init__(remoteOpBuilder)
		self._conditionBuilderFunc = conditionBuilderFunc

	def __enter__(self):
		super().__enter__()
		# Add a new loop block instruction to start the while loop 
		self._newLoopBlockInstructionIndex = self._rob._addInstruction(
			lowLevel.InstructionType.NewLoopBlock,
			RelativeOffset(1), # offset updated in __exit__ method
			RelativeOffset(1)
		)
		# Generate the loop condition instructions and enter the if block.
		condition = self._conditionBuilderFunc()
		self._ifBlock = self._rob.ifBlock(condition)
		self._ifBlock.__enter__()

	def __exit__(self, exc_type, exc_val, exc_tb):
		# Add a jump instruction to the end of the body to jump back to the start of the loop block.
		relativeContinueOffset = self._newLoopBlockInstructionIndex - self._rob._lastInstructionIndex
		self._rob._addInstruction(
			lowLevel.InstructionType.Fork,
			RelativeOffset(relativeContinueOffset)
		)
		#Complete the if block.
		self._ifBlock.__exit__(exc_type, exc_val, exc_tb)
		# Add an end loop block instruction after the if block. 
		self._rob._addInstruction(
			lowLevel.InstructionType.EndLoopBlock ,
		)
		# Update the break offset of the new loop block instruction to jump to after the end loop block instruction.
		nextInstructionIndex = self._rob._lastInstructionIndex + 1
		relativeBreakOffset = nextInstructionIndex - self._newLoopBlockInstructionIndex
		newLoopBlockInstruction = self._rob._getInstructionRecord(self._newLoopBlockInstructionIndex)
		newLoopBlockInstruction.params[0].value = relativeBreakOffset
		super().__exit__(exc_type, exc_val, exc_tb)


class _RemoteTryBlockBuilder(_RemoteScope):

	def __enter__(self):
		super().__enter__()
		self._newTryBlockInstructionIndex = self._rob._addInstruction(
			lowLevel.InstructionType.NewTryBlock,
			RelativeOffset(1), # offset updated in __exit__ method
		)
		super().__enter__()

	def __exit__(self, exc_type, exc_val, exc_tb):
		# Add an end try block instruction after the try block. 
		self._rob._addInstruction(
			lowLevel.InstructionType.EndTryBlock ,
		)
		# Update the catchoffset of the new try block instruction to jump to after the end try block instruction.
		nextInstructionIndex = self._rob._lastInstructionIndex + 1
		relativeCatchOffset = nextInstructionIndex - self._newTryBlockInstructionIndex
		newTryBlockInstruction = self._rob._getInstructionRecord(self._newTryBlockInstructionIndex)
		newTryBlockInstruction.params[0].value = relativeCatchOffset
		super().__exit__(exc_type, exc_val, exc_tb)


class _RemoteCatchBlockBuilder(_RemoteScope):

	def __init__(self, remoteOpBuilder: RemoteOperationBuilder):
		super().__init__(remoteOpBuilder)

	def __enter__(self):
		if not isinstance(self._rob._scopeJustExited, _RemoteTryBlockBuilder):
			raise RuntimeError("Catch block not directly preceded by Try block")
		tryScope = self._rob._scopeJustExited
		super().__enter__()
		# Add a jump instruction directly after the try block to skip over the catch block.
		self._jumpInstructionIndex = self._rob._addInstruction(
			lowLevel.InstructionType.Fork,
			RelativeOffset(1), # offset updated in __exit__ method
		)
		# Increment the catch offset of the try block to take the new jump instruction into account.
		newTryBlockInstruction = self._rob._getInstructionRecord(tryScope._newTryBlockInstructionIndex)
		newTryBlockInstruction.params[0].value += 1

	def __exit__(self, exc_type, exc_val, exc_tb):
		# Update the jump instruction to jump to the real end of the catch block.
		nextInstructionIndex = self._rob._lastInstructionIndex + 1
		relativeJumpOffset = nextInstructionIndex - self._jumpInstructionIndex
		jumpInstruction = self._rob._getInstructionRecord(self._jumpInstructionIndex)
		jumpInstruction.params[0].value = relativeJumpOffset
		super().__exit__(exc_type, exc_val, exc_tb)
