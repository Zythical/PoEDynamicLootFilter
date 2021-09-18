#NoEnv
#SingleInstance Force
SendMode Input
SetWorkingDir %A_ScriptDir%

; File Paths for Python program/input/output
py_prog_path:= "backend_cli.py"
py_out_path:="backend_cli.output"
ahk_out_path:="backend_cli.input"

; Valid item types
curr_valid := ["Exalted Orb", "Orb of Alteration" , "Blessed Orb" , "Blacksmith's Whetstone" , "Armourer's Scrap" , "Glassblower's Bauble" , "Orb of Transmutation" , "Orb of Augmentation" , "Scroll of Wisdom" , "Portal Scroll" , "Chromatic Orb" , "Jeweller's Orb" , "Orb of Chance" , "Orb of Alchemy" , "Orb of Binding" , "Orb of Fusing" , "Vaal Orb" , "Orb of Horizons" , "Cartographer's Chisel" , "Regal Orb" , "Orb of Regret" , "Orb of Scouring" , "Gemcutter's Prism" ]
validstr := ""
for idx, val in curr_valid
	validstr .= "|" val
rare_valid := ["WeaponsX", "Weapons3","Body Armours","Helmets","Gloves","Boots","Amulets","Rings","Belts"]
validstr2 := ""
for idx,val in rare_valid
	validstr2 .= "|" val
; Coloring from consts.py
rare_colors := {"Weapons" : "c80000", "Body Armours" : "ff00ff", "Helmets" : "ff7200", "Gloves" : "ffe400", "Boots" : "00ff00", "Amulets" : "00ffff", "Rings" : "4100bd", "Belts" : "0000c8"}
; Flask stuff
flasks := {"Quicksilver Flask":[0,0], "Bismuth Flask":[0,0], "Amethyst Flask":[0,0], "Ruby Flask":[0,0], "Sapphire Flask":[0,0], "Topaz Flask":[0,0], "Aquamarine Flask":[0,0], "Diamond Flask":[0,0], "Jade Flask":[0,0], "Quartz Flask":[0,0], "Granite Flask":[0,0], "Sulphur Flask":[0,0], "Basalt Flask":[0,0], "Silver Flask":[0,0], "Stibnite Flask":[0,0], "Corundum Flask":[0,0], "Gold Flask":[0,0]}

; Read starting filter data from python client
curr_txt := []
curr_ids := []
curr_val := []
curr_val_start := []
rare_txt := []
rare_ids := []
rare_val := []
rare_val_start := []
fake_queue := []
profiles := []
FileDelete, %ahk_out_path%
RunWait, python %py_prog_path% get_all_profile_names, , Hide
FileRead, py_out_text, %py_out_path%
Loop, parse, py_out_text, `n, `r
{
	If(A_LoopField = "")
		continue
	profiles.push(A_LoopField)
}
active_profile := profiles[1]
FileAppend, get_all_currency_tiers`nget_all_chaos_recipe_statuses`nget_hide_maps_below_tier`nget_currency_tier_visibility tportal`nget_currency_tier_visibility twisdom`nget_hide_currency_above_tier`nget_hide_uniques_above_tier`nget_gem_min_quality`n, %ahk_out_path%
For key in flasks
{
	FileAppend, is_flask_rule_enabled_for "%key%"`r`n, %ahk_out_path% 
	fake_queue.Push(key)
}
RunWait, python %py_prog_path% run_batch %active_profile%, , Hide
FileRead, py_out_text, %py_out_path%
prog := 0
Loop, parse, py_out_text, `n, `r
{
	If(A_LoopField = "")
		continue
	If(InStr(A_LoopField, "@"))
	{
		prog := prog + 1
		continue
	}
	Switch prog
	{
	Case 0:
		splits := StrSplit(A_LoopField, ";")
		If(InStr(validstr, splits[1])){
			curr_txt.Push(splits[1])
			curr_val.Push(splits[2])
			curr_val_start.Push(splits[2])
		}
	Case 1:
		splits := StrSplit(A_LoopField, ";")
		If(InStr(validstr2, splits[1]))
		{
			rare_txt.Push(splits[1])
			rare_val.Push(splits[2])
			rare_val_start.Push(splits[2])
		}
	Case 2:
		maphide := A_LoopField
	Case 3:
		base_porthide := !A_LoopField
		PortalHide := base_porthide
	Case 4:
		base_wishide := !A_LoopField
		WisdomHide := base_wishide
	Case 5:
		currhide := A_LoopField
	Case 6:
		uniqhide := A_LoopField
	Case 7:
		gemmin := A_LoopField
		base_gemmin := gemmin
	Default:
		flasks[fake_queue[prog - 6]] := [A_LoopField, A_LoopField]
	}
}
; Initialize GUI Handles for changing text items
for idx in curr_txt
{
	curr_ids.Push("curr_id_" idx)
}
for idx in rare_txt
{
	rare_ids.Push("rare_id_" idx)
}

;********** GUI Start ******************************
GuiBuild:
; Currency
Gui, Font, S16 cB0B0B0 norm, Courier New
height:= 0
For idx, val in curr_txt
{
	height := -20 + 25 * idx
	Gui, Add, Text, x250 y%height% grmbhack, % Format("{:-24}",val)
	Gui, Add, Text, % "backgroundtrans x" 545 " y" height " v" curr_ids[idx], % curr_val[idx]
}
; Buttons
Gui, Font, S20 cB0B0B0 norm bold, Courier New
;height := height - 32
height := 473
Gui, Add, Button, x867 y%height% gUpdate_ BackgroundTrans, Update
Gui, Add, Button, x13 y%height% gCancel_ BackgroundTrans, Cancel

; Profiles DDL
Gui, Font, S18 cB0B0B0 norm bold, Courier New
ProfString := ""
for key, val in profiles
	ProfString .= val "|"
RTrim(ProfString, "|")
Gui, Add, DropDownList, w235 x5 y5 Choose1 vProf gProfDDL, % ProfString

; Rares
Gui, Font, S18 norm bold, Courier New
height := 0
For idx, val in rare_txt
{
	height := 10 + 40  * idx
	Gui, Font, % "c" rare_colors[val]
	Gui, Add, Text, backgroundtrans x10 y%height% grmbhack, % Format("{:-16}", val)
	Gui, Font, S36, Wingdings
	Gui, Font, % "c" (rare_val[idx]? "Blue" : "Red")
	Gui, Add, Text, % "w40 backgroundtrans x" 200 " y" (height - 10) " v" rare_ids[idx], % (rare_val[idx]? Chr(252) : Chr(251))
	Gui, Font, S18 norm bold, Courier New
}
; Misc
Gui, Font, S18 norm cB0B0B0, Courier New
height := 10

; Portal/Wisdom
if (PortalHide)
	Gui, Font, Strike
Gui, Add, Text, x590 y%height% grmbhack vPortalHide, Portal Scroll
Gui, Font, norm
if (WisdomHide)
	Gui, Font, Strike
Gui, Add, Text, x790 y%height% grmbhack vWisdomHide, Wisdom Scroll
Gui, Font, norm
height := height + 30

; Hide Map Tiers
Gui, Add, Text, x590 y%height% grmbhack BackgroundTrans, % "Hide Maps Below Tier:           "
Gui, Add, Text, x944 y%height% w40 BackgroundTrans vMapTierHide, % Format("{:2}", maphide)
height := height + 30

; Hide Currency Tiers
Gui, Add, Text, x590 y%height% grmbhack BackgroundTrans, % "Hide Currency Above Tier:       "
Gui, Add, Text, x944 y%height% w40 BackgroundTrans vCurrTierHide, % Format("{:2}", currhide)
height := height + 30

; Hide Unique Tiers
Gui, Add, Text, x590 y%height% grmbhack BackgroundTrans, % "Hide Uniques Above Tier:        "
Gui, Add, Text, x944 y%height% w40 BackgroundTrans vUniqTierHide, % Format("{:2}", uniqhide)
height := height + 30


; Gem Qual
Gui, Add, Text, x590 y%height% vgemtext, Minimum Gem Quality: %gemmin%`%
height := height + 30
Gui, Add, Slider, Range1-20 ToolTip NoTicks x590 y%height% gGemSlider vgemslider AltSubmit, % gemmin
height := height + 20

; Flask DDL
Gui, Add, Text, x590 y%height%, Enable/Disable Flasks:
height := height + 30
FlaskShow := -1
FlaskString := ""
for key, val in flasks
	FlaskString .= key "|"
RTrim(FlaskString, "|")
Gui, Add, DropDownList, x590 y%height% vFlask gFlaskDDL, % FlaskString
Gui, Font, c606060
Gui, Add, Text, % "x865 y" height + 5 " grmbhack", Hacky
Gui, Font, S36, Wingdings
Gui, Add, Text, % "backgroundtrans x865 w40 y" height-7 " vFlaskShow", 

; Rule Matching
Gui, Font, S14 norm cB0B0B0, Courier New
height := height + 40
Gui, Add, Button, x590 y%height% gClip_, Find Rule Matching Clipboard

; Options
Gui, -border
Gui, Color, 606060
Gui, Show, w1000
return
;************** GUI END **************************************

; Both RMB and LMB lead here
rmbhack:
GuiContextMenu:
control_ := RTrim(A_GuiControl)
For idx, val in curr_txt
{
	If (control_ = val)
	{
		;GuiControlGet, current,,% curr_ids[idx]
		current := curr_val[idx]
		If (A_GuiEvent = "RightClick")
			current := (current = 1? 1 : current - 1)
		Else
			current := (current = 9? 9 : current + 1)
		GuiControl,,% curr_ids[idx], % current
		curr_val[idx] := current
		return
	}
}
For idx, val in rare_txt
{
	If (control_ = val)
	{
		;GuiControlGet, current,,% rare_ids[idx]
		rare_val[idx]:= !rare_val[idx]
		GuiControl, % "+c" (rare_val[idx]? "Blue" : "Red"), % rare_ids[idx]
		GuiControl,,% rare_ids[idx], % (rare_val[idx]? Chr(252) : Chr(251))
		return
	}
}
If (control_ = "Hide Maps Below Tier:")
{
	GuiControlGet, current,, MapTierHide
	If (A_GuiEvent = "RightClick")
		current := (current = 1? 1 : current - 1)
	Else
		current := (current = 16? 16 : current + 1)
	GuiControl,, MapTierHide, % Format("{:2}", current)
	return
}
If (control_ = "Hide Currency Above Tier:")
{
	GuiControlGet, current,, CurrTierHide
	If (A_GuiEvent = "RightClick")
		current := (current = 1? 1 : current - 1)
	Else
		current := (current = 9? 9 : current + 1)
	GuiControl,, CurrTierHide, % Format("{:2}", current)
	return
}
If (control_ = "Hide Uniques Above Tier:")
{
	GuiControlGet, current,, UniqTierHide
	If (A_GuiEvent = "RightClick")
		current := (current <= 1? 1 : current - 1)
	Else
		current := (current >= 5? 5 : current + 1)
	GuiControl,, UniqTierHide, % Format("{:2}", current)
	return
}
If (control_ = "Hacky" and not FlaskShow = -1)
{
	FlaskShow := !FlaskShow
	flasks[Flask][1] := FlaskShow
	GuiControl, % "+c" (FlaskShow? "Blue" : "Red"), FlaskShow
	GuiControl,, FlaskShow, % (FlaskShow? Chr(252) : Chr(251))
}
If (control_ = "PortalHide")
{
	Gui, Font, S18 cB0B0B0 norm, Courier New
	PortalHide := !PortalHide
	if (PortalHide)
		Gui, Font, Strike
	GuiControl, Font, PortalHide
}
If (control_ = "WisdomHide")
{
	Gui, Font, S18 cB0B0B0 norm, Courier New
	WisdomHide := !WisdomHide
	if (WisdomHide)
		Gui, Font, Strike
	GuiControl, Font, WisdomHide
}
return

; Flask Dropdown List
FlaskDDL:
Gui, Submit, NoHide
FlaskShow := flasks[Flask][1]
GuiControl, % "+c" (FlaskShow? "Blue" : "Red"), FlaskShow
GuiControl,, FlaskShow, % (FlaskShow? Chr(252) : Chr(251))
return

; Profile Dropdown List
ProfDDL:
Gui, Submit, NoHide
If (Prof = active_profile)
	return
RunWait, python %py_prog_path% set_active_profile %Prof%, , Hide
Reload
ExitApp

; Gem Slider
GemSlider:
Gui, Submit, NoHide
gemmin := gemslider
GuiControl,, gemtext, Minimum Gem Quality: %gemmin%`%
return

; ???
MsgBox(Message := "Press Ok to Continue.", Title := "", Type := 0, B1 := "", B2 := "", B3 := "", Time := "") {
	If (Title = "")
		Title := A_ScriptName
	If (B1 != "") || (B2 != "") || (B3 != "")
		SetTimer, ChangeButtonNames, -10
	MsgBox, % Type, % Title, % Message, % Time
	Return

	ChangeButtonNames:
		IfWinNotExist, %Title%
			Return
		WinActivate, % Title
		ControlSetText, Button1, % (B1 = "") ? "Ok" : B1, % Title
		Try ControlSetText, Button2, % (B2 = "") ? "Cancel" : B2, % Title
		Try ControlSetText, Button3, % (B3 = "") ? "Close" : B3, % Title
	Return
}

; Clipboard Rule Matching
Clip_:
FileDelete, %ahk_out_path%
FileDelete, %py_out_path%
FileAppend, % Clipboard, %ahk_out_path%
RunWait, python %py_prog_path% get_rule_matching_item %active_profile%, , Hide
FileRead, py_out_text, %py_out_path%
If( py_out_text = "")
{
	MsgBox, No Matched Rule
	return
}
idx := 0
type_tag := ""
tier_tag := ""
rule := ""
Loop, parse, py_out_text, `n, `r
{
	if(idx = 0){
		splits := StrSplit(A_LoopField, ":")
		type_tag := splits[2]
		idx := 1
	}
	else if(idx = 1){
		splits := StrSplit(A_LoopField, ":")
		tier_tag := splits[2]
		idx := 2
	}
	else
		rule .= A_LoopField "`n"
}
visi := ""
If(InStr(py_out_text, "Show #")){
	MsgBox(rule, "Matched Rule" , 3 , "Hide", "Disable", "Show")
	IfMsgBox Yes
		visi := "hide"
	IfMsgBox No
		visi := "disable"
}Else If(InStr(py_out_text, "Hide #")){
	MsgBox(rule, "Matched Rule" , 3 , "Show", "Disable", "Hide")
	IfMsgBox Yes
		visi := "show"
	IfMsgBox No
		visi := "disable"
}Else{
	MsgBox(rule, "Matched Rule" , 3 , "Show", "Hide", "Disable")
	IfMsgBox Yes
		visi := "show"
	IfMsgBox No
		visi := "hide"
}
If(visi != ""){
	RunWait, python %py_prog_path% set_rule_visibility "%type_tag%" %tier_tag% %visi% %active_profile%, , Hide
}
return

; Write all filter modifications to one file, send it over to python
Update_:
Gui, Hide
FileDelete, %ahk_out_path%
for idx in curr_txt
{
	if(curr_val[idx] != curr_val_start[idx])
		FileAppend, % "set_currency_tier """ curr_txt[idx] """ " curr_val[idx] "`n" , %ahk_out_path%
	curr_val_start[idx] := curr_val[idx]
}
for idx in rare_txt
{
	if(rare_val[idx] != rare_val_start[idx])
		FileAppend, % "set_chaos_recipe_enabled_for """rare_txt[idx] """ " rare_val[idx] "`n", %ahk_out_path%
	rare_val_start[idx] := rare_val[idx]
}
GuiControlGet, current_currhide,, CurrTierHide
GuiControlGet, current_maphide,, MapTierHide
GuiControlGet, current_uniqhide,, UniqTierHide
if (current_currhide != currhide)
	FileAppend, % "set_hide_currency_above_tier " current_currhide "`n", %ahk_out_path%
 currhide := current_currhide
if (current_maphide != maphide)
	FileAppend, % "set_hide_map_below_tier " current_maphide "`n", %ahk_out_path%
maphide := current_maphide
if (current_uniqhide != uniqhide)
	FileAppend, % "set_hide_uniques_above_tier " current_uniqhide "`n", %ahk_out_path%
uniqhide := current_uniqhide
if (base_porthide != PortalHide){
	FileAppend, % "set_currency_tier_visibility tportal " (PortalHide? "0":"1") "`n", %ahk_out_path%
}
base_porthide := PortalHide
if (base_wishide != WisdomHide){
	FileAppend, % "set_currency_tier_visibility twisdom " (WisdomHide? "0":"1") "`n", %ahk_out_path%
}
base_wishide := WisdomHide
if (base_gemhide != gemhide){
	FileAppend, % "set_gem_min_quality " %gemhide% "`n", %ahk_out_path%
}
base_gemhide := gemhide
for idx, val in flasks
{
	if (val[1] != val[2])
	{
		FileAppend, % "set_flask_rule_enabled_for """ idx """ " val[1] "`n", %ahk_out_path%
	}
	val[2] = val[1]
}
RunWait, python %py_prog_path% run_batch %active_profile%, , Hide
Gui, 1: Hide
return
;ExitApp

Cancel_:
Gui, Hide
return
;ExitApp

F7::
Gui, 1: Show, Restore
;Reload
return
;ExitApp

F12::
Run, python %py_prog_path% import_downloaded_filter %active_profile%,  , Hide
Reload
ExitApp