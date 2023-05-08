# A part of NonVisual Desktop Access (NVDA)
# Copyright (C) 2022-2023 NV Access Limited
# This file is covered by the GNU General Public License.
# See the file COPYING for more details.

from typing import (
	Callable,
	Dict,
	List,
)

import wx
from wx.lib.expando import ExpandoTextCtrl

from _addonStore.models.addon import (
	AddonStoreModel,
)
from gui import guiHelper
from gui.dpiScalingHelper import DpiScalingHelperMixinWithoutInit
from logHandler import log

from ..viewModels.addonList import (
	AddonDetailsVM,
	AddonActionVM,
)


_fontFaceName = "Segoe UI"
_fontFaceName_semiBold = "Segoe UI Semibold"


class AddonDetails(
		wx.Panel,
		DpiScalingHelperMixinWithoutInit,
):
	# Translators: Header (usually the add-on name) when no add-on is selected. In the add-on store dialog.
	_noAddonSelectedLabelText: str = pgettext("addonStore", "No add-on selected.")

	# Translators: Label for the text control containing a description of the selected add-on.
	# In the add-on store dialog.
	_descriptionLabelText: str = pgettext("addonStore", "Description:")

	# Translators: Label for the text control containing a description of the selected add-on.
	# In the add-on store dialog.
	_statusLabelText: str = pgettext("addonStore", "Status:")

	# Translators: Label for the text control containing a description of the selected add-on.
	# In the add-on store dialog.
	_actionsLabelText: str = pgettext("addonStore", "Actions:")

	def __init__(self, parent, actionVMList: List[AddonActionVM], detailsVM: AddonDetailsVM):
		self._detailsVM: AddonDetailsVM = detailsVM
		self._actionVMList = actionVMList
		wx.Panel.__init__(
			self,
			parent,
			style=wx.TAB_TRAVERSAL | wx.BORDER_THEME
		)

		selfSizer = wx.BoxSizer(wx.VERTICAL)
		self.SetSizer(selfSizer)
		parentSizer = wx.BoxSizer(wx.VERTICAL)
		# To make the text fields less ugly.
		# See Windows explorer file properties dialog for an example.
		self.SetBackgroundColour(wx.Colour("white"))

		self.addonNameCtrl = wx.StaticText(
			self,
			style=wx.ALIGN_CENTRE_HORIZONTAL | wx.ST_NO_AUTORESIZE
		)
		self.updateAddonName(AddonDetails._noAddonSelectedLabelText)
		self._setAddonNameCtrlStyle()
		selfSizer.Add(self.addonNameCtrl, flag=wx.EXPAND)
		selfSizer.Add(
			parentSizer,
			border=guiHelper.BORDER_FOR_DIALOGS,
			proportion=1,  # make vertically stretchable
			flag=(
				wx.EXPAND  # make horizontally stretchable
				| wx.ALL  # and make border all around
			),
		)

		self.contents = wx.BoxSizer(wx.VERTICAL)
		self.contentsPanel = wx.Panel(self)
		self.contentsPanel.SetSizer(self.contents)
		parentSizer.Add(self.contentsPanel, proportion=1, flag=wx.EXPAND | wx.ALL)

		self.contents.AddSpacer(guiHelper.SPACE_BETWEEN_VERTICAL_DIALOG_ITEMS)

		# It would be nice to override the name using wx.Accessible,
		# but using it on a TextCtrl breaks the accessibility of the control entirely (all state/role is reset)
		# Instead, add a hidden label for the textBox, Windows exposes this as the accessible name.
		self.descriptionLabel = wx.StaticText(
			self.contentsPanel,
			label=AddonDetails._descriptionLabelText
		)
		self.contents.Add(self.descriptionLabel, flag=wx.EXPAND)
		self.descriptionLabel.Hide()
		self.descriptionTextCtrl = wx.TextCtrl(
			self.contentsPanel,
			style=(
				0  # purely to allow subsequent items to line up.
				| wx.TE_MULTILINE  # details will require multiple lines
				| wx.TE_READONLY  # the details shouldn't be user editable
				| wx.BORDER_NONE
			)
		)
		panelWidth = 500
		descriptionMinSize = wx.Size(self.scaleSize((panelWidth, 100)))
		descriptionMaxSize = wx.Size(self.scaleSize((panelWidth, 800)))
		self.descriptionTextCtrl.SetMinSize(descriptionMinSize)
		self.descriptionTextCtrl.SetMaxSize(descriptionMaxSize)
		self.contents.Add(self.descriptionTextCtrl, flag=wx.EXPAND)
		self.contents.Add(wx.StaticLine(self.contentsPanel), flag=wx.EXPAND)

		self.statusLabel = wx.StaticText(
			self.contentsPanel,
			label=AddonDetails._statusLabelText
		)
		self.statusTextCtrl = ExpandoTextCtrl(
			self.contentsPanel,
			style=wx.TE_READONLY | wx.BORDER_NONE,
		)
		self.contents.Add(self.statusLabel)
		self.contents.Add(self.statusTextCtrl, flag=wx.EXPAND)

		self.contents.AddSpacer(guiHelper.SPACE_BETWEEN_VERTICAL_DIALOG_ITEMS)
		self.contents.Add(wx.StaticLine(self.contentsPanel), flag=wx.EXPAND)
		self.contents.AddSpacer(guiHelper.SPACE_BETWEEN_VERTICAL_DIALOG_ITEMS)

		self._actionButtonMap: Dict[AddonActionVM, wx.Button] = {}
		self.actionButtonSizer = wx.WrapSizer()
		self.actionButtonPanel = wx.Panel(self.contentsPanel)
		self.actionButtonPanel.SetSizer(self.actionButtonSizer)
		self.contents.Add(self.actionButtonPanel)
		self._createActionButtons()

		self.contents.AddSpacer(guiHelper.SPACE_BETWEEN_VERTICAL_DIALOG_ITEMS)
		self.contents.Add(wx.StaticLine(self.contentsPanel), flag=wx.EXPAND)
		self.contents.AddSpacer(guiHelper.SPACE_BETWEEN_VERTICAL_DIALOG_ITEMS)

		# It would be nice to override the name using wx.Accessible,
		# but using it on a TextCtrl breaks the accessibility of the control entirely (all state/role is reset)
		# Instead, add a hidden label for the textBox, Windows exposes this as the accessible name.
		self.otherDetailsLabel = wx.StaticText(
			self.contentsPanel,
			# Translators: Label for the text control containing extra details about the selected add-on.
			# In the add-on store dialog.
			label=pgettext("addonStore", "&Other Details:")
		)
		self.contents.Add(self.otherDetailsLabel, flag=wx.EXPAND)
		self.otherDetailsLabel.Hide()
		self.otherDetailsTextCtrl = wx.TextCtrl(
			self.contentsPanel,
			size=self.scaleSize((panelWidth, 400)),
			style=(
				0  # purely to allow subsequent items to line up.
				| wx.TE_MULTILINE  # details will require multiple lines
				| wx.TE_READONLY  # the details shouldn't be user editable
				| wx.TE_RICH2
				| wx.TE_NO_VSCROLL  # No scroll by default.
				| wx.BORDER_NONE
			)
		)
		self._createRichTextStyles()
		self.contents.Add(self.otherDetailsTextCtrl, flag=wx.EXPAND, proportion=1)
		self._refresh()  # ensure that the visual state matches.
		self._detailsVM.updated.register(self._updatedListItem)
		self.Layout()

	def _createRichTextStyles(self):
		# Set up the text styles for the "other details" (which contains several fields)
		# Note, wx seems to merge text styles when using 'SetDefaultStyle',
		# so if color is used in one text attr, the others need to override it also.
		# If this isn't done and E.G. style1 doesn't specify color, style2 is blue, then
		# setting style1 as the default style will continue to result in blue text.
		self.defaultStyle = wx.TextAttr()
		self.defaultStyle.SetFontFaceName(_fontFaceName)
		self.defaultStyle.SetTextColour("black")
		self.defaultStyle.SetFontSize(10)

		self.labelStyle = wx.TextAttr(self.defaultStyle)
		# Note: setting font weight doesn't seem to work for RichText, instead specify via the font face name
		self.labelStyle.SetFontFaceName(_fontFaceName_semiBold)

	def _setAddonNameCtrlStyle(self):
		addonNameFont: wx.Font = self.addonNameCtrl.GetFont()
		addonNameFont.SetPointSize(18)
		# Note: setting font weight via the font face name doesn't seem to work on staticText
		# set explicitly using SetWeight
		addonNameFont.SetWeight(wx.FONTWEIGHT_BOLD)
		addonNameFont.SetFaceName(_fontFaceName)
		self.addonNameCtrl.SetFont(addonNameFont)
		self.addonNameCtrl.SetForegroundColour("white")
		nvdaPurple = wx.Colour((71, 47, 95))
		self.addonNameCtrl.SetBackgroundColour(nvdaPurple)

	def updateAddonName(self, displayName: str):
		self.addonNameCtrl.SetLabelText(displayName)
		self.SetLabel(displayName)

	def _updatedListItem(self, addonDetailsVM: AddonDetailsVM):
		log.debug(f"Setting listItem: {addonDetailsVM.listItem}")
		assert self._detailsVM.listItem == addonDetailsVM.listItem
		self._refresh()

	def _refresh(self):
		details = None if self._detailsVM.listItem is None else self._detailsVM.listItem.model
		status = None if self._detailsVM.listItem is None else self._detailsVM.listItem.status

		with guiHelper.autoThaw(self):
			# AppendText is used to build up the details so that formatting can be set as text is added, via
			# SetDefaultStyle, however, this means the text control must start empty.
			self.otherDetailsTextCtrl.SetValue("")
			if not details:
				self.contentsPanel.Hide()
				self.updateAddonName(AddonDetails._noAddonSelectedLabelText)
			else:
				self.updateAddonName(details.displayName)
				self.descriptionLabel.SetLabelText(AddonDetails._descriptionLabelText)
				# For a ExpandoTextCtr, SetDefaultStyle can not be used to set the style (along with the use
				# of AppendText) because AppendText has been overridden to use SetValue(GetValue()+newStr)
				# which drops formatting. Instead, set the text, then the style.
				self.descriptionTextCtrl.SetValue(details.description)
				self.descriptionTextCtrl.SetStyle(
					0,
					self.descriptionTextCtrl.GetLastPosition(),
					self.defaultStyle
				)

				if status:
					self.statusTextCtrl.SetValue(status.displayString)

				self._appendDetailsLabelValue(
					# Translators: Label for an extra detail field for the selected add-on. In the add-on store dialog.
					pgettext("addonStore", "Publisher:"),
					details.publisher
				)
				self._appendDetailsLabelValue(
					# Translators: Label for an extra detail field for the selected add-on. In the add-on store dialog.
					pgettext("addonStore", "Version:"),
					details.addonVersionName
				)
				self._appendDetailsLabelValue(
					# Translators: Label for an extra detail field for the selected add-on. In the add-on store dialog.
					pgettext("addonStore", "Channel:"),
					details.channel
				)
				if isinstance(details, AddonStoreModel):
					self._appendDetailsLabelValue(
						# Translators: Label for an extra detail field for the selected add-on. In the add-on store dialog.
						pgettext("addonStore", "License:"),
						details.license
					)

				incompatibleReason = details.getIncompatibleReason()
				if incompatibleReason:
					self._appendDetailsLabelValue(
						# Translators: Label for an extra detail field for the selected add-on. In the add-on store dialog.
						pgettext("addonStore", "Incompatible Reason:"),
						incompatibleReason
					)
				self.contentsPanel.Show()

		self.Layout()
		# Set caret/insertion point at the beginning so that NVDA users can more easily read from the start.
		self.otherDetailsTextCtrl.SetInsertionPoint(0)

	def _addDetailsLabel(self, label: str):
		detailsTextCtrl = self.otherDetailsTextCtrl
		detailsTextCtrl.SetDefaultStyle(self.labelStyle)
		detailsTextCtrl.AppendText(label)
		detailsTextCtrl.SetDefaultStyle(self.defaultStyle)

	def _appendDetailsLabelValue(self, label: str, value: str):
		detailsTextCtrl = self.otherDetailsTextCtrl

		if detailsTextCtrl.GetValue():
			detailsTextCtrl.AppendText('\n')

		self._addDetailsLabel(label)
		labelSpace = " "  # em space, wider than regular space, for visual layout.

		detailsTextCtrl.SetDefaultStyle(self.defaultStyle)
		detailsTextCtrl.AppendText(labelSpace)
		detailsTextCtrl.AppendText(value)

	def _createActionButtons(self) -> None:
		def _makeButtonClickedEventHandler(_action: AddonActionVM) -> Callable[[wx.CommandEvent, ], None]:
			"""Get around python binding to the latest value in a for loop, create a new lambda
			for each value with an explicit binding to the addon details.
			"""
			def handleButtonClickEvent(event: wx.CommandEvent) -> None:
				_action.actionHandler(self._detailsVM.listItem)
				# set focus on status so that is easily read after firing an action
				self.statusTextCtrl.SetFocus()

			return handleButtonClickEvent

		for action in self._actionVMList:
			button = wx.Button(self.actionButtonPanel, label=action.displayName)
			self.actionButtonSizer.Add(button)
			button.Bind(
				event=wx.EVT_BUTTON,
				handler=_makeButtonClickedEventHandler(action)
			)
			button.Show(show=action.isValid)
			action.updated.register(self._actionVmChanged)
			self._actionButtonMap[action] = button

	def _actionVmChanged(self, addonActionVM: AddonActionVM):
		self._actionButtonMap[addonActionVM].Show(show=addonActionVM.isValid)
		if self._detailsVM.listItem:
			self.statusTextCtrl.SetValue(self._detailsVM.listItem.status.displayString)
		self.Layout()
