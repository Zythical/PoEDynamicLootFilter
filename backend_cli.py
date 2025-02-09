'''
This file defines the command-line interface for the AHK frontend
to call the Python backend.  The general call format is:

 > python3 backend_cli.py <function_name> <function_parameters...> <profile_name (if required)>

Return values of functions will be placed in the file "backend_cli.output",
formatted as specified by the frontend developer.  (Note: make sure
calls to the cli are synchronous if return values are to be used,
so you ensure data is written before you try to read it.)

Some functions do not require a profile_name parameter, specifically those which
do not interact with the filter in any way (for now, this is simply the setters and getters
for profile names).

Scroll down to DelegateFunctionCall() to see documentation of all supported functions.
   
The input and output filter filepaths are specified in config.py.
(Eventually these will be the same, but for testing they're distinct.)

Error handling:  if anything goes wrong while the python script is executing,
all relevant error messages will be written to "backend_cli.log", since the
standard output will not be available when the scripts are run via AHK.
For example, running the following command:
 > python3 backend_cli.py adjust_currency_tier "Chromatic Orb" a
will generate the error message:
"ValueError: invalid literal for int() with base 10: 'a'",
which will be logged to the log file along with the stack trace.

Testing feature:
 - Insert "TEST" as the first argument after "python3 backend_cli.py" to run tests
 - This wil write output to test output filter, rather than the PathOfExile filter path
 - This will also save all profile updates in a separate testing profile so as to not ruin
   one's real profile(s).  Used in all test_suite.py calls.
'''

from collections import OrderedDict
import os
from pathlib import Path
import shlex
import shutil
import sys
import traceback
from typing import List

import consts
import file_manip
import helper
import logger
from loot_filter import RuleVisibility, LootFilterRule, LootFilter
import profile
from type_checker import CheckType, CheckType2

kLogFilename = 'backend_cli.log'
kInputFilename = 'backend_cli.input'
kOutputFilename = 'backend_cli.output'
kExitCodeFilename = 'backend_cli.exit_code'

# Map of function name -> dictionary of properties indexed by the following string keywords:
# - HasProfileParam: bool
# - ModifiesFilter: bool
# - NumParamsForMatch: int, only present for functions that modify the filter,
#   Tells how many parameters need to be the same for two functions of this name to be
#   reducible to a single function in the profile changes file.  For example:
#     > adjust_currency_tier "Chromatic Orb" +1
#     > adjust_currency_tier "Chromatic Orb" +1
#   is reducible to
#     > adjust_currency_tier "Chromatic Orb" +2
#   so this value would be 1 for 'adjust_currency_tier'.
kFunctionInfoMap = {
    # Profiles
    'is_first_launch' : {
        'HasProfileParam' : False,
        'ModifiesFilter' : False,
    },
    'get_all_profile_names' : {
        'HasProfileParam' : False,
        'ModifiesFilter' : False,
    },
    'create_new_profile' : { 
        'HasProfileParam' : False,
        'ModifiesFilter' : False,
    },
    'set_active_profile' : { 
        'HasProfileParam' : False,
        'ModifiesFilter' : False,
    },
    # General
    'import_downloaded_filter' : { 
        'HasProfileParam' : True,
        'ModifiesFilter' : False,
    },
    'run_batch' : { 
        'HasProfileParam' : True,
        'ModifiesFilter' : False,
    },
    'get_rule_matching_item' : { 
        'HasProfileParam' : True,
        'ModifiesFilter' : False,
    },
    'set_rule_visibility' : { 
        'HasProfileParam' : True,
        'ModifiesFilter' : True,
        'NumParamsForMatch' : 2,
    },
    # Currency
    'set_currency_to_tier' : { 
        'HasProfileParam' : True,
        'ModifiesFilter' : True,
        'NumParamsForMatch' : 1,
    },
    'get_tier_of_currency' : { 
        'HasProfileParam' : True,
        'ModifiesFilter' : False,
    },
    'get_all_currency_tiers' : { 
        'HasProfileParam' : True,
        'ModifiesFilter' : False,
    },
    'set_currency_tier_min_visible_stack_size' : {
        'HasProfileParam' : True,
        'ModifiesFilter' : True,
        'NumParamsForMatch' : 1,
    },
    'get_currency_tier_min_visible_stack_size' : { 
        'HasProfileParam' : True,
        'ModifiesFilter' : False,
    },
    # Archnemesis
    'set_archnemesis_mod_tier' : { 
        'HasProfileParam' : True,
        'ModifiesFilter' : True,
        'NumParamsForMatch' : 1,
    },
    'get_all_archnemesis_mod_tiers' : { 
        'HasProfileParam' : True,
        'ModifiesFilter' : False,
    },
    # Essences
    'get_all_essence_tier_visibilities' : { 
        'HasProfileParam' : True,
        'ModifiesFilter' : False,
    },
    'set_hide_essences_above_tier' : { 
        'HasProfileParam' : True,
        'ModifiesFilter' : True,
        'NumParamsForMatch' : 0,
    },
    'get_hide_essences_above_tier' : { 
        'HasProfileParam' : True,
        'ModifiesFilter' : False,
    },
    # Divination Cards
    'get_all_div_card_tier_visibilities' : { 
        'HasProfileParam' : True,
        'ModifiesFilter' : False,
    },
    'set_hide_div_cards_above_tier' : { 
        'HasProfileParam' : True,
        'ModifiesFilter' : True,
        'NumParamsForMatch' : 0,
    },
    'get_hide_div_cards_above_tier' : { 
        'HasProfileParam' : True,
        'ModifiesFilter' : False,
    },
    # Unique Items
    'get_all_unique_item_tier_visibilities' : { 
        'HasProfileParam' : True,
        'ModifiesFilter' : False,
    },
    'set_hide_unique_items_above_tier' : { 
        'HasProfileParam' : True,
        'ModifiesFilter' : True,
        'NumParamsForMatch' : 0,
    },
    'get_hide_unique_items_above_tier' : { 
        'HasProfileParam' : True,
        'ModifiesFilter' : False,
    },
    # Unique Maps
    'get_all_unique_map_tier_visibilities' : { 
        'HasProfileParam' : True,
        'ModifiesFilter' : False,
    },
    'set_hide_unique_maps_above_tier' : { 
        'HasProfileParam' : True,
        'ModifiesFilter' : True,
        'NumParamsForMatch' : 0,
    },
    'get_hide_unique_maps_above_tier' : { 
        'HasProfileParam' : True,
        'ModifiesFilter' : False,
    },
    # Oils
    'set_lowest_visible_oil' : { 
        'HasProfileParam' : True,
        'ModifiesFilter' : True,
        'NumParamsForMatch' : 0,
    },
    'get_lowest_visible_oil' : { 
        'HasProfileParam' : True,
        'ModifiesFilter' : False,
    },
    # Quality Gems
    'set_gem_min_quality' : { 
        'HasProfileParam' : True,
        'ModifiesFilter' : True,
        'NumParamsForMatch' : 0,
    },
    'get_gem_min_quality' : { 
        'HasProfileParam' : True,
        'ModifiesFilter' : False,
    },
    # Quality Flasks
    'set_flask_min_quality' : { 
        'HasProfileParam' : True,
        'ModifiesFilter' : True,
        'NumParamsForMatch' : 0,
    },
    'get_flask_min_quality' : { 
        'HasProfileParam' : True,
        'ModifiesFilter' : False,
    },
    # Hide Maps Below Tier
    'set_hide_maps_below_tier' : { 
        'HasProfileParam' : True,
        'ModifiesFilter' : True,
        'NumParamsForMatch' : 0,
    },
    'get_hide_maps_below_tier' : { 
        'HasProfileParam' : True,
        'ModifiesFilter' : False,
    },
    # Flasks Types
    'set_flask_visibility' : { 
        'HasProfileParam' : True,
        'ModifiesFilter' : True,
        'NumParamsForMatch' : 1,
    },
    'set_high_ilvl_flask_visibility' : { 
        'HasProfileParam' : True,
        'ModifiesFilter' : True,
        'NumParamsForMatch' : 1,
    },
    'get_flask_visibility' : { 
        'HasProfileParam' : True,
        'ModifiesFilter' : False,
    },
    'get_all_flask_visibilities' : { 
        'HasProfileParam' : True,
        'ModifiesFilter' : False,
        'NumParamsForMatch' : 0,
    },
    # RGB Items
    'set_rgb_item_max_size' : { 
        'HasProfileParam' : True,
        'ModifiesFilter' : True,
        'NumParamsForMatch' : 0,
    },
    'get_rgb_item_max_size' : { 
        'HasProfileParam' : True,
        'ModifiesFilter' : False,
    },
    # Chaos Recipe
    'set_chaos_recipe_enabled_for' : { 
        'HasProfileParam' : True,
        'ModifiesFilter' : True,
        'NumParamsForMatch' : 1,
    },
    'is_chaos_recipe_enabled_for' : { 
        'HasProfileParam' : True,
        'ModifiesFilter' : False,
    },
    'get_all_chaos_recipe_statuses' : { 
        'HasProfileParam' : True,
        'ModifiesFilter' : False,
    },
}

# Functions that don't require a profile parameter in the CLI
# These are the functions that do not interact with the loot filter in any way
kNoProfileParameterFunctionNames = [
        'get_all_profile_names', 'create_new_profile', 'set_active_profile']

def Error(e):
    logger.Log('Error ' + str(e))
    raise RuntimeError(e)
# End Error

def FileExists(path: str) -> bool:
    return Path(path).is_file()
# End FileExists

def CheckNumParams(params_list: List[str], required_num_params: int):
    CheckType(params_list, 'params_list', list)
    CheckType(required_num_params, 'required_num_params', int)
    if (len(params_list) != required_num_params):
        error_message: str = ('incorrect number of parameters given for '
                              'function {}: required {}, got {}').format(
                                   sys.argv[1], required_num_params, len(params_list))
        Error(error_message)
# End CheckNumParams

def WriteOutput(output_string: str):
    CheckType(output_string, 'output_string', str)
    with open(kOutputFilename, 'w') as output_file:
        output_file.write(output_string)
# End WriteOutput

# function_output_string should be the whole string containing the given function call's output
def AppendFunctionOutput(function_output_string: str):
    CheckType(function_output_string, 'function_output_string', str)
    with open(kOutputFilename, 'a') as output_file:
        output_file.write(function_output_string + '\n@\n')
# End AppendFunctionOutput

def AddFunctionToChangesDict(function_tokens: List[str], changes_dict: OrderedDict):
    CheckType2(function_tokens, 'function_tokens', list, str)
    CheckType(changes_dict, 'changes_dict', OrderedDict)
    function_name = function_tokens[0]
    num_params_for_match = kFunctionInfoMap[function_name]['NumParamsForMatch']
    current_dict = changes_dict
    for i in range(num_params_for_match + 1):
        current_token = function_tokens[i]
        if (i == num_params_for_match):
            current_dict[current_token] = function_tokens[i + 1]
        else:
            if (current_token not in current_dict):
                current_dict[current_token] = OrderedDict()
            current_dict = current_dict[current_token]
# End AddLineToChangesDict

# Returns list of lists of function tokens, for example:
# [['adjust_currency_tier', 'Chromatic Orb', '1'],
#  ['hide_uniques_above_tier', '3']]
def ConvertChangesDictToFunctionListRec(changes_dict: OrderedDict or str,
                                        current_prefix_list: List[str] = []) -> list:
    CheckType(changes_dict, 'changes_dict', (OrderedDict, str))
    CheckType2(current_prefix_list, 'current_prefix_list', list, str)
    # changes_dict may just be final parameter, in which case it's a string
    if (isinstance(changes_dict, str)):
        last_param: str = changes_dict
        return [current_prefix_list + [last_param]]
    # Otherwise, recursively handle all keys in changes_dict
    result_list = []
    for param, subdict in changes_dict.items():
        result_list.extend(
                ConvertChangesDictToFunctionListRec(subdict, current_prefix_list + [param]))
    return result_list
# End ConvertChangesDictToFunctionListRec

def ConvertChangesDictToFunctionList(changes_dict: OrderedDict) -> list:
    CheckType(changes_dict, 'changes_dict', OrderedDict)
    # Get list of lists of function tokens from recursive function above
    token_lists = ConvertChangesDictToFunctionListRec(changes_dict)
    function_list = []
    for token_list in token_lists:
        function_list.append(helper.JoinParams(token_list))
    return function_list
# End ConvertChangesDictToFunctionList

def UpdateProfileChangesFile(changes_fullpath: str,
                             new_function_name: str,
                             new_function_params: list):
    CheckType(changes_fullpath, 'changes_fullpath', str)
    CheckType(new_function_name, 'new_function_name', str)
    CheckType2(new_function_params, 'new_function_params', list, str)
    # Parse changes file as chain of OrderedDicts:
    # function_name -> param1 -> param2 -> ... -> last_param
    #  > set_currency_tier "Chaos Orb" 3
    # 'set_currency_tier' -> 'Chaos Orb' -> '3':
    # {'set_currency_tier' : {'Chaos Orb' : '3'}}
    parsed_changes_dict = OrderedDict()
    changes_lines_list = helper.ReadFile(changes_fullpath)
    for line in changes_lines_list:
        tokens_list = shlex.split(line.strip())
        AddFunctionToChangesDict(tokens_list, parsed_changes_dict)
    # Now check if new function matches with any functions in parsed_changes_dict
    num_params_for_match = kFunctionInfoMap[new_function_name]['NumParamsForMatch']
    match_flag: bool = new_function_name in parsed_changes_dict
    matched_rule_tokens_list = [new_function_name]
    if (match_flag):
        current_dict = parsed_changes_dict[new_function_name]
        for i in range(num_params_for_match):
            current_param = new_function_params[i]
            if (current_param not in current_dict):
                match_flag = False
                break
            else:
                matched_rule_tokens_list.append(current_param)
                current_dict = current_dict[current_param]
        # Append last parameter if we found a match
        # A bit wacky, but current_dict is just last parameter here due to the last line above
        if (match_flag):
            matched_rule_tokens_list.append(current_dict)
    # If we found a match, we update the matched function in the changes_dict,
    # combining matching functions by simply overwriting the last parameter
    # If we didn't find a match, we instead just add the new function to our changes_dict
    # Either way, the following line of code does exactly what we want:
    AddFunctionToChangesDict([new_function_name] + new_function_params, parsed_changes_dict)
    # Convert our parsed_changes_dict into a list of functions
    changes_list = ConvertChangesDictToFunctionList(parsed_changes_dict)
    # Write updated profile changes
    helper.WriteToFile(changes_list, changes_fullpath)
# End UpdateProfileChangesFile

def DelegateFunctionCall(loot_filter: LootFilter or None,
                         function_name: str,
                         function_params: List[str],
                         *,  # require subsequent arguments to be named in function call
                         in_batch: bool = False,
                         suppress_output: bool = False):
    CheckType(loot_filter, 'loot_filter', (LootFilter, type(None)))
    CheckType(function_name, 'function_name', str)
    CheckType(function_params, 'function_params_list', list)
    CheckType(in_batch, 'in_batch', bool)
    CheckType(suppress_output, 'suppress_output', bool)
    # Alias config_data for convenience
    config_data = loot_filter.profile_config_data if loot_filter else None
    # 
    output_string = ''
    # Save function call to profile data if it is a mutator function
    # Note: suppress_output also functioning as an indicator to not save profile data here
    if (kFunctionInfoMap[function_name]['ModifiesFilter'] and not suppress_output):
        # We use the syntax some_list[:] to create a copy of some_list
        UpdateProfileChangesFile(config_data['ChangesFullpath'], function_name, function_params[:])
    # =============================== Import Downloaded Filter ===============================
    if (function_name == 'import_downloaded_filter'):
        '''
        import_downloaded_filter <optional keyword: "only_if_missing">
         - Reads the filter located in the downloads directory, applies all DLF
           custom changes to it, and saves the result in the Path Of Exile directory.
         - If the argument "only_if_missing" is present, does nothing if the filter already is
           present in the Path of Exile filters directory.
         - Assumes this is NOT called as part of a batch
         - Output: None
         - Example: > python3 backend_cli.py import_downloaded_filter
         - Example: > python3 backend_cli.py import_downloaded_filter only_if_missing
        '''
        import_flag = True
        if ((len(function_params) == 1) and (function_params[0] == 'only_if_missing')):
            import_flag = not FileExists(config_data['OutputLootFilterFullpath'])
        else:
            CheckNumParams(function_params, 0)
        if (import_flag):
            loot_filter.ApplyImportChanges()
            changes_lines: List[str] = helper.ReadFile(config_data['ChangesFullpath'])
            for function_call_string in changes_lines:
                _function_name, *_function_params = shlex.split(function_call_string)
                DelegateFunctionCall(loot_filter, _function_name, _function_params,
                                     in_batch = True, suppress_output = True)
            loot_filter.SaveToFile()
    # ======================================= Run Batch =======================================
    # Note: cannot run_batch from within a run_batch command, as there would be no place for
    # batch function call list, and this should be unnecessary
    elif ((function_name == 'run_batch') and not in_batch):
        '''
        run_batch
         - Runs the batch of functions specified in file backend_cli.input
         - Format is one function call per line, given as: <function_name> <function_params...>
         - Output: concatenation of the outputs of all the functions, with each function output
           separated by the line containing the single character: `@`
         - Example: > python3 run_batch
        '''
        CheckNumParams(function_params, 0)
        WriteOutput('')  # clear the output file, since we will be appending output in batch
        contains_mutator = False
        function_call_list: List[str] = helper.ReadFile(kInputFilename)
        for function_call_string in function_call_list:
            if (function_call_string.strip() == ''):
                continue
            # need different variable names here to not overwrite the existing ones
            _function_name, *_function_params = shlex.split(function_call_string)
            if (kFunctionInfoMap[_function_name]['ModifiesFilter']):
                contains_mutator = True
            DelegateFunctionCall(loot_filter, _function_name, _function_params,
                                 in_batch = True, suppress_output = False)
        # Check if batch contained a mutator and save filter if so
        if (contains_mutator):
            loot_filter.SaveToFile()
    # ========================================== Profile ==========================================
    elif (function_name == 'is_first_launch'):
        '''
        is_first_launch
         - Output: "1" if this is the first launch of the program (i.e. requires setup),
           "0" otherwise
         - It is considered first launch iff the only profile is DefaultProfile
         - Example: > python3 backend_cli.py is_first_launch
        '''
        CheckNumParams(function_params, 0)
        profile_names_list = profile.GetAllProfileNames()
        is_first_launch_flag: bool = (profile_names_list == ['DefaultProfile'])
        output_string = str(int(is_first_launch_flag))
    elif (function_name == 'get_all_profile_names'):
        '''
        get_all_profile_names
         - Output: newline-separated list of all profile names, with currently active profile first
         - If there is no specified active profile (e.g. if general.config is missing), first line
           will be blank
         - Example: > python3 backend_cli.py get_all_profile_names
        '''
        CheckNumParams(function_params, 0)
        profile_names_list = profile.GetAllProfileNames()
        output_string += '\n'.join(profile_names_list)
    elif (function_name == 'create_new_profile'):
        '''
        create_new_profile <new_profile_name>
         - Creates a new profile from the config values given in backend_cli.input
         - Each input line takes the form: "<keyword>:<value>", with keywords defined in profile.py
         - Required keywords: 'DownloadDirectory', 'PathOfExileDirectory', 'DownloadedLootFilterFilename'
         - Does nothing if a profile with the given new_profile_name already exists
         - Output: "1" if the new profile was created, "0" otherwise
         - Example: > python3 backend_cli.py create_new_profile MyProfile
        '''
        CheckNumParams(function_params, 1)
        new_profile_name = function_params[0]
        config_values: dict = helper.ReadFileToDict(kInputFilename)
        created_profile = profile.CreateNewProfile(new_profile_name, config_values)
        output_string += str(int(created_profile != None))
    elif (function_name == 'set_active_profile'):
        '''
        set_active_profile <new_active_profile_name>
         - Note: Does *not* take a (current) <profile_name> parameter
         - Raises an error if new_active_profile_name does not exist
         - Output: None
         - Example: > python3 backend_cli.py set_active_profile TestProfile
        '''
        CheckNumParams(function_params, 1)
        profile.SetActiveProfile(function_params[0])
    # ====================================== Rule Matching ======================================
    elif (function_name == 'get_rule_matching_item'):
        '''
        get_rule_matching_item
         - Takes an item text as input in backend_cli.input
         - Finds the rule in the PoE filter matching the item and writes it to backend_cli.output
         - The first two lines of output will be `type_tag:<type_tag>` and `tier_tag:<tier_tag>`,
           these two tags together form a unique key for the rule
         - Ignores rules with AreaLevel conditions, as well as many other niche keywords
         - Socket rules only implemented as numeric counting for now, ignores color requirements
         - Example: > python3 backend_cli.py get_rule_matching_item DefaultProfile
        '''
        CheckNumParams(function_params, 0)
        item_text_lines: List[str] = helper.ReadFile(kInputFilename)
        type_tag, tier_tag = loot_filter.GetRuleMatchingItem(item_text_lines)
        output_string = 'type_tag:{}\ntier_tag:{}\n'.format(str(type_tag), str(tier_tag))
        if ((type_tag != None) and (tier_tag != None)):
            matched_rule = loot_filter.GetRuleByTypeTier(type_tag, tier_tag)
            output_string += '\n'.join(matched_rule.text_lines)        
    elif (function_name == 'set_rule_visibility'):
        '''
        set_rule_visibility <type_tag: str> <tier_tag: str> <visibility: {show, hide, disable}>
         - Shows, hides, or disables the rule specified by the given type and tier tags
         - The visibility parameter is one of: `show`, `hide`, `disable`
         - Output: None (for now, can output a success flag if needed)
         - Example > python3 backend_cli.py set_rule_visibility "rare->redeemer" t12 show
         - Note: quotes (either type) are necessary for tags containing a ">" character,
           since the shell will normally iterpret as the output redirection signal
         - Example: > python3 backend_cli.py set_rule_visibility uniques 5link 0 DefaultProfile
        '''
        CheckNumParams(function_params, 3)
        type_tag, tier_tag, visibility_string = function_params
        kVisibilityMap = {'show': RuleVisibility.kShow, 'hide': RuleVisibility.kHide,
                          'disable': RuleVisibility.kDisable}
        success_flag = loot_filter.SetRuleVisibility(
                type_tag, tier_tag, kVisibilityMap[visibility_string])
        # Error out on incorrect tags for now to make testing easierlensing
        if (not success_flag):
            Error('Rule with type_tag="{}", tier_tag="{}" does not exist in filter'.format(
                    type_tag, tier_tag))
    # ======================================== Currency ========================================
    elif (function_name == 'set_currency_to_tier'):
        '''
        set_currency_to_tier <currency_name: str> <tier: int>
         - Moves the given currency type to the specified tier for all unstacked and stacked rules
         - Output: None
         - Example: > python3 backend_cli.py set_currency_to_tier "Chromatic Orb" 5 DefaultProfile
        '''
        CheckNumParams(function_params, 2)
        currency_name: str = function_params[0]
        target_tier: int = int(function_params[1])
        loot_filter.SetCurrencyToTier(currency_name, target_tier)
    elif (function_name == 'get_tier_of_currency'):
        '''
        get_tier_of_currency <currency_name: str>
         - Output: tier (int) containing the given currency type
         - Example: > python3 backend_cli.py get_tier_of_currency "Chromatic Orb" DefaultProfile
        '''
        CheckNumParams(function_params, 1)
        currency_name: str = function_params[0]
        output_string = str(loot_filter.GetTierOfCurrency(currency_name))
    elif (function_name == 'get_all_currency_tiers'):
        '''
        get_all_currency_tiers
         - Output: newline-separated sequence of `<currency_name: str>;<tier: int>`
         - Example: > python3 backend_cli.py get_all_currency_tiers DefaultProfile
        '''
        CheckNumParams(function_params, 0)
        for tier in range(1, consts.kNumCurrencyTiersExcludingScrolls + 1):
            currency_names = loot_filter.GetAllCurrencyInTier(tier)
            output_string += ''.join((currency_name + ';' + str(tier) + '\n')
                                        for currency_name in currency_names)
        if (output_string[-1] == '\n'): output_string = output_string[:-1]  # remove final newline
    elif (function_name == 'set_currency_tier_min_visible_stack_size'):
        '''
        set_currency_tier_min_visible_stack_size <tier: int or string> <stack_size: int or "hide_all">
         - Shows currency stacks >= stack_size and hides stacks < stack_size for the given tier
         - If stack_size is "hide_all", all currency of the given tier will be hidden
         - Valid stack_size values: {1, 2, 4} for tiers1-7, {1, 2, 4, 6} for tiers 8-9 and scrolls
         - tier is an integer [1-9] or "tportal"/"twisdom" for Portal/Wisdom Scrolls
         - Output: None
         - Example: > python3 backend_cli.py set_currency_min_visible_stack_size 7 6 DefaultProfile
         - Example: > python3 backend_cli.py set_currency_min_visible_stack_size twisdom hide_all DefaultProfile
        '''
        CheckNumParams(function_params, 2)
        tier_str: str = function_params[0]
        min_stack_size_str: str = function_params[1]
        loot_filter.SetCurrencyTierMinVisibleStackSize(tier_str, min_stack_size_str)
    elif (function_name == 'get_currency_tier_min_visible_stack_size'):
        '''
        get_currency_tier_min_visible_stack_size <tier: int or str>
         - "tier" is an int, or "tportal"/"twisdom" for portal/wisdom scrolls
         - Output: min visible stack size for the given currency tier
         - Example: > python3 backend_cli.py get_currency_tier_min_visible_stack_size 4 DefaultProfile
         - Example: > python3 backend_cli.py get_currency_tier_min_visible_stack_size twisdom DefaultProfile
        '''
        CheckNumParams(function_params, 1)
        tier_str: str = function_params[0]
        output_string = str(loot_filter.GetCurrencyTierMinVisibleStackSize(tier_str))
    # ===================================== Archnemesis Mods =====================================
    elif (function_name == 'set_archnemesis_mod_tier'):
        '''
        set_archnemesis_mod_tier <archnemesis_mod_name: str> <tier: int>
         - Moves the given archnemesis mod to the specified tier
         - Note: use last tier (4) to hide specific mod
         - Output: None
         - Example: > python3 backend_cli.py set_archnemesis_mod_tier "Frenzied" 1 DefaultProfile
         - Example: > python3 backend_cli.py set_archnemesis_mod_tier "Gargantuan" 4 DefaultProfile
        '''
        CheckNumParams(function_params, 2)
        archnemesis_mod_name: str = function_params[0]
        target_tier: int = int(function_params[1])
        loot_filter.SetArchnemesisModToTier(archnemesis_mod_name, target_tier)
    elif (function_name == 'get_all_archnemesis_mod_tiers'):
        '''
        get_all_archnemesis_mod_tiers
         - Output: newline-separated sequence of `<archnemesis_mod_name: str>;<tier: int>`
           Note: last tier is a "hide" tier
         - Example: > python3 backend_cli.py get_all_archnemesis_mod_tiers DefaultProfile
        '''
        CheckNumParams(function_params, 0)
        for tier in range(1, consts.kNumArchnemesisTiers):  # omit last tier, as it's hide all
            archnemesis_mod_names = loot_filter.GetAllArchnemesisModsInTier(tier)
            output_string += ''.join((archnemesis_mod_name + ';' + str(tier) + '\n')
                                        for archnemesis_mod_name in archnemesis_mod_names)
        if ((len(output_string) > 0) and (output_string[-1] == '\n')):
            output_string = output_string[:-1]  # remove final newline
    # ========================================= Essences =========================================
    elif (function_name == 'get_all_essence_tier_visibilities'):
        '''
        get_all_essence_tier_visibilities
         - Output: newline-separated sequence of `<tier>;<visible_flag>`, one per tier
         - <tier> is an integer representing the tier, <visibile_flag> is 1/0 for True/False
         - Example: > python3 backend_cli.py get_all_essence_tier_visibilities DefaultProfile
        '''
        CheckNumParams(function_params, 0)
        for tier in range(1, consts.kNumEssenceTiers + 1):
            output_string += str(tier) + ';' + str(int(
                    loot_filter.GetEssenceTierVisibility(tier) == RuleVisibility.kShow)) + '\n'
        if (output_string[-1] == '\n'): output_string = output_string[:-1]  # remove final newline
    elif (function_name == 'set_hide_essences_above_tier'):
        '''
        set_hide_essences_above_tier <tier: int>
         - Sets the essence tier "above" which all will be hidden
           (higher essence tiers are worse)
         - Output: None
         - Example: > python3 backend_cli.py set_hide_essences_above_tier 3 DefaultProfile
        '''
        CheckNumParams(function_params, 1)
        max_visible_tier: int = int(function_params[0])
        loot_filter.SetHideEssencesAboveTierTier(max_visible_tier)
    elif (function_name == 'get_hide_essences_above_tier'):
        '''
        get_hide_essences_above_tier
         - Output: single integer, the tier above which all essences are hidden
         - Example: > python3 backend_cli.py get_hide_essences_above_tier DefaultProfile
        '''
        CheckNumParams(function_params, 0)
        output_string = str(loot_filter.GetHideEssencesAboveTierTier())
    # ========================================= Div Cards =========================================
    elif (function_name == 'get_all_div_card_tier_visibilities'):
        '''
        get_all_div_card_tier_visibilities
         - Output: newline-separated sequence of `<tier>;<visible_flag>`, one per tier
         - <tier> is an integer representing the tier, <visibile_flag> is 1/0 for True/False
         - Example: > python3 backend_cli.py get_all_div_card_tier_visibilities DefaultProfile
        '''
        CheckNumParams(function_params, 0)
        for tier in range(1, consts.kNumDivCardTiers + 1):
            output_string += str(tier) + ';' + str(int(
                    loot_filter.GetDivCardTierVisibility(tier) == RuleVisibility.kShow)) + '\n'
        if (output_string[-1] == '\n'): output_string = output_string[:-1]  # remove final newline
    elif (function_name == 'set_hide_div_cards_above_tier'):
        '''
        set_hide_div_cards_above_tier <tier: int>
         - Sets the essence tier "above" which all will be hidden
           (higher tiers are worse)
         - Output: None
         - Example: > python3 backend_cli.py set_hide_essences_above_tier 3 DefaultProfile
        '''
        CheckNumParams(function_params, 1)
        max_visible_tier: int = int(function_params[0])
        loot_filter.SetHideDivCardsAboveTierTier(max_visible_tier)
    elif (function_name == 'get_hide_div_cards_above_tier'):
        '''
        get_hide_div_cards_above_tier
         - Output: single integer, the tier above which all essences are hidden
         - Example: > python3 backend_cli.py get_hide_div_cards_above_tier DefaultProfile
        '''
        CheckNumParams(function_params, 0)
        output_string = str(loot_filter.GetHideDivCardsAboveTierTier())
    # ======================================= Unique Items =======================================
    elif (function_name == 'get_all_unique_item_tier_visibilities'):
        '''
        get_all_unique_item_tier_visibilities
         - Output: newline-separated sequence of `<tier>;<visible_flag>`, one per tier
         - <tier> is an integer representing the tier, <visibile_flag> is 1/0 for True/False
         - Example: > python3 backend_cli.py get_all_unique_item_tier_visibilities DefaultProfile
        '''
        CheckNumParams(function_params, 0)
        for tier in range(1, consts.kNumUniqueItemTiers + 1):
            output_string += str(tier) + ';' + str(int(
                    loot_filter.GetUniqueItemTierVisibility(tier) == RuleVisibility.kShow)) + '\n'
        if (output_string[-1] == '\n'): output_string = output_string[:-1]  # remove final newline
    elif (function_name == 'set_hide_unique_items_above_tier'):
        '''
        set_hide_unique_items_above_tier <tier: int>
         - Sets the unique item tier "above" which all will be hidden
           (higher tiers are less valuable)
         - Output: None
         - Example: > python3 backend_cli.py set_hide_unique_items_above_tier 3 DefaultProfile
        '''
        CheckNumParams(function_params, 1)
        max_visible_tier: int = int(function_params[0])
        loot_filter.SetHideUniqueItemsAboveTierTier(max_visible_tier)
    elif (function_name == 'get_hide_unique_items_above_tier'):
        '''
        get_hide_unique_items_above_tier
         - Output: single integer, the tier above which all unique items are hidden
         - Example: > python3 backend_cli.py get_hide_unique_items_above_tier DefaultProfile
        '''
        CheckNumParams(function_params, 0)
        output_string = str(loot_filter.GetHideUniqueItemsAboveTierTier())
    # ======================================= Unique Maps =======================================
    elif (function_name == 'get_all_unique_map_tier_visibilities'):
        '''
        get_all_unique_map_tier_visibilities
         - Output: newline-separated sequence of `<tier>;<visible_flag>`, one per tier
         - <tier> is an integer representing the tier, <visibile_flag> is 1/0 for True/False
         - Example: > python3 backend_cli.py get_all_unique_map_tier_visibilities DefaultProfile
        '''
        CheckNumParams(function_params, 0)
        for tier in range(1, consts.kNumUniqueMapTiers + 1):
            output_string += str(tier) + ';' + str(int(
                    loot_filter.GetUniqueMapTierVisibility(tier) == RuleVisibility.kShow)) + '\n'
        if (output_string[-1] == '\n'): output_string = output_string[:-1]  # remove final newline
    elif (function_name == 'set_hide_unique_maps_above_tier'):
        '''
        set_hide_unique_maps_above_tier <tier: int>
         - Sets the unique map tier "above" which all will be hidden
           (higher tiers are less valuable)
         - Output: None
         - Example: > python3 backend_cli.py set_hide_unique_maps_above_tier 3 DefaultProfile
        '''
        CheckNumParams(function_params, 1)
        max_visible_tier: int = int(function_params[0])
        loot_filter.SetHideUniqueMapsAboveTierTier(max_visible_tier)
    elif (function_name == 'get_hide_unique_maps_above_tier'):
        '''
        get_hide_unique_maps_above_tier
         - Output: single integer, the tier above which all unique maps are hidden
         - Example: > python3 backend_cli.py get_hide_unique_maps_above_tier DefaultProfile
        '''
        CheckNumParams(function_params, 0)
        output_string = str(loot_filter.GetHideUniqueMapsAboveTierTier())
    # ======================================= Blight Oils =======================================
    elif (function_name == 'set_lowest_visible_oil'):
        '''
        set_lowest_visible_oil <oil_name: str>
         - Sets the lowest-value blight oil which to be shown
         - Output: None
         - Example: > python3 backend_cli.py set_lowest_visible_oil "Violet Oil" DefaultProfile
        '''
        CheckNumParams(function_params, 1)
        loot_filter.SetLowestVisibleOil(function_params[0])
    elif (function_name == 'get_lowest_visible_oil'):
        '''
        get_lowest_visible_oil
         - Output: the name of the lowest-value blight oil that is shown
         - Example: > python3 backend_cli.py get_lowest_visible_oil DefaultProfile
        '''
        CheckNumParams(function_params, 0)
        output_string = loot_filter.GetLowestVisibleOil()
    # ======================================= Gem Quality =======================================
    elif (function_name == 'set_gem_min_quality'):
        '''
        set_gem_min_quality <quality: int in [1, 20]>
         - Sets the minimum quality below which gems will not be shown by gem quality rules
         - Output: None
         - Example: > python3 backend_cli.py set_gem_min_quality 10 DefaultProfile
        '''
        CheckNumParams(function_params, 1)
        min_quality: int = int(function_params[0])
        loot_filter.SetGemMinQuality(min_quality)
    elif (function_name == 'get_gem_min_quality'):
        '''
        get_gem_min_quality
         - Output: single integer, minimum shown gem quality for gem quality rules
         - Example: > python3 backend_cli.py get_gem_min_quality DefaultProfile
        '''
        CheckNumParams(function_params, 0)
        output_string = str(loot_filter.GetGemMinQuality())
    # ====================================== Flask Quality ======================================
    elif (function_name == 'set_flask_min_quality'):
        '''
        set_flask_min_quality <quality: int in [1, 20]>
         - Sets the minimum quality below which flasks will not be shown by flask quality rules
         - Output: None
         - Example: > python3 backend_cli.py set_flask_min_quality 14 DefaultProfile
        '''
        CheckNumParams(function_params, 1)
        min_quality: int = int(function_params[0])
        loot_filter.SetFlaskMinQuality(min_quality)
    elif (function_name == 'get_flask_min_quality'):
        '''
        get_flask_min_quality
         - Output: single integer, minimum shown flask quality for flask quality rules
         - Example: > python3 backend_cli.py get_flask_min_quality DefaultProfile
        '''
        CheckNumParams(function_params, 0)
        output_string = str(loot_filter.GetFlaskMinQuality())
    # ========================================== Maps ==========================================
    elif (function_name == 'set_hide_maps_below_tier'):
        '''
        set_hide_maps_below_tier <tier: int>
         - Sets the map tier below which all will be hidden (use 0/1 to show all)
         - Output: None
         - Example: > python3 backend_cli.py set_hide_maps_below_tier 14 DefaultProfile
        '''
        min_visibile_tier: int = int(function_params[0])
        loot_filter.SetHideMapsBelowTierTier(min_visibile_tier)
    elif (function_name == 'get_hide_maps_below_tier'):
        '''
        get_hide_maps_below_tier
         - Output:  single integer, the tier below which all maps are hidden
         - Example: > python3 backend_cli.py get_hide_maps_below_tier DefaultProfile
        '''
        output_string = str(loot_filter.GetHideMapsBelowTierTier())
    # ========================================= Flasks =========================================
    elif (function_name == 'set_flask_visibility'):
        '''
        set_flask_visibility <base_type: str> <visibility_flag: int>
         - Note: this does not overwrite any original filter rules, only adds a rule on top.
           This function never hides flasks, it only modifies its own "Show" rule.
         - <base_type> is any valid flask BaseType
         - enable_flag is 1 for True (visible), 0 for False (not included in DLF rule)
         - Output: None
         - Example: > python3 backend_cli.py set_flask_rule_enabled_for "Quartz Flask" 1 DefaultProfile
        '''
        flask_base_type: str = function_params[0]
        enable_flag: bool = bool(int(function_params[1]))
        high_ilvl_flag: bool = False
        loot_filter.SetFlaskRuleEnabledFor(flask_base_type, enable_flag, high_ilvl_flag)
    elif (function_name == 'set_high_ilvl_flask_visibility'):
        '''
        set_high_ilvl_flask_visibility <base_type: str> <visibility_flag: int>
         - Note: this does not overwrite any original filter rules, only adds a rule on top.
           This function never hides flasks, it only modifies its own "Show" rule.
         - "High" item level threshold is defined in consts.py, currently 85
         - <base_type> is any valid flask BaseType
         - enable_flag is 1 for True (visible), 0 for False (not included in DLF rule)
         - Output: None
         - Example: > python3 backend_cli.py set_high_ilvl_flask_rule_enabled_for "Quartz Flask" 1 DefaultProfile
        '''
        flask_base_type: str = function_params[0]
        enable_flag: bool = bool(int(function_params[1]))
        high_ilvl_flag: bool = True
        loot_filter.SetFlaskRuleEnabledFor(flask_base_type, enable_flag, high_ilvl_flag)
    elif (function_name == 'get_flask_visibility'):
        '''
        get_flask_visibility <base_type: str>
         - <base_type> is any valid flask BaseType
         - Output: "1" if given flask base type is shown by DLF rule, else "0"
         - Example: > python3 backend_cli.py is_flask_rule_enabled_for "Quicksilver Flask" DefaultProfile
        '''
        flask_base_type: str = function_params[0]
        high_ilvl_flag: bool = False
        generic_rule_visibility_flag = \
                loot_filter.IsFlaskRuleEnabledFor(flask_base_type, high_ilvl_flag)
        high_ilvl_flag: bool = True
        high_ilvl_rule_visibility_flag = \
                loot_filter.IsFlaskRuleEnabledFor(flask_base_type, high_ilvl_flag)
        output_string = (str(int(generic_rule_visibility_flag)) + ' ' +
                         str(int(high_ilvl_rule_visibility_flag)))
    # TODO: Update this for new high ilvl flask rules
    elif (function_name == 'get_all_flask_visibilities'):
        '''
        get_all_flask_visibilities
         - Output: newline-separated sequence of <flask_basetype>;<visibility_flag: int>
         - visibility_flag is 1 for True (visible), 0 for False (not included in DLF rule)
         - Example: > python3 backend_cli.py get_all_enabled_flask_types DefaultProfile
        '''
        visible_flask_types = loot_filter.GetAllVisibleFlaskTypes(False)
        visible_flask_types_set = set(visible_flask_types)
        for visible_flask_base_type in visible_flask_types:
            output_string += visible_flask_base_type + ';1' + '\n'
        for flask_base_type in consts.kAllFlaskTypes:
            if flask_base_type not in visible_flask_types_set:
                output_string += flask_base_type + ';0' + '\n'
        if (output_string[-1] == '\n'): output_string = output_string[:-1]  # remove final newline
    # ======================================== Rgb Items ========================================
    elif (function_name == 'set_rgb_item_max_size'):
        '''
        set_rgb_item_max_size <size: {none, small, medium, large}>
         - Sets the maximum size at which an RGB item is shown
         - "small" = 4, "medium" = 6, "large" = 8
         - Output: None
         - Example: > python3 backend_cli.py set_rgb_item_max_size small DefaultProfile
        '''
        rgb_item_max_size: str = function_params[0]
        loot_filter.SetRgbItemMaxSize(rgb_item_max_size)
    elif (function_name == 'get_rgb_item_max_size'):
        '''
        get_rgb_item_max_size
         - Output:  max-size of shown RGB items, one of {none, small, medium, large}
         - Example: > python3 backend_cli.py get_rgb_item_max_size DefaultProfile
        '''
        output_string = loot_filter.GetRgbItemMaxSize()
    # =================================== Chaos Recipe Rares ===================================
    elif (function_name == 'set_chaos_recipe_enabled_for'):
        '''
        set_chaos_recipe_enabled_for <item_slot: str> <enable_flag: int>
         - <item_slot> is one of: "Weapons", "Body Armours", "Helmets", "Gloves",
           "Boots", "Amulets", "Rings", "Belts"
         - enable_flag is 1 for True (enable), 0 for False (disable)
         - Output: None
         - Example: > python3 backend_cli.py set_chaos_recipe_enabled_for Weapons 0 DefaultProfile
        '''
        item_slot: str = function_params[0]
        enable_flag: bool = bool(int(function_params[1]))
        loot_filter.SetChaosRecipeEnabledFor(item_slot, enable_flag)
    elif (function_name == 'is_chaos_recipe_enabled_for'):
        '''
        is_chaos_recipe_enabled_for <item_slot: str>
         - <item_slot> is one of: "Weapons", "Body Armours", "Helmets", "Gloves",
           "Boots", "Amulets", "Rings", "Belts"  (defined in consts.py)
         - Output: "1" if chaos recipe items are showing for the given item_slot, else "0"
         - Example: > python3 backend_cli.py is_chaos_recipe_enabled_for "Body Armours" DefaultProfile
        '''
        item_slot: str = function_params[0]
        output_string = str(int(loot_filter.IsChaosRecipeEnabledFor(item_slot)))
    elif (function_name == 'get_all_chaos_recipe_statuses'):
        '''
        get_all_chaos_recipe_statuses
         - Output: one line formatted as `<item_slot>;<enabled_flag>` for each item slot
         - <item_slot> is one of: "Weapons", "Body Armours", "Helmets", "Gloves",
           "Boots", "Amulets", "Rings", "Belts"
         - <enabled_flag> is "1" if chaos recipe items are showing for given item_slot, else "0"
         - Example: > python3 backend_cli.py get_all_chaos_recipe_statuses DefaultProfile
        '''
        for item_slot in consts.kChaosRecipeItemSlots:
            enabled_flag_string = str(int(loot_filter.IsChaosRecipeEnabledFor(item_slot)))
            output_string += item_slot + ';' + enabled_flag_string + '\n'
        if (output_string[-1] == '\n'): output_string = output_string[:-1]  # remove final newline
    # ================================= Unmatched Function Name =================================
    else:
        error_message: str = 'Function "{}" not found'.format(function_name)
        logger.Log('Error: ' + error_message)
        raise RuntimeError(error_message)
    # ============================= End Function Call Delegation ================================
    # Return value is now in output_string
    if (in_batch):
        if (not suppress_output): AppendFunctionOutput(output_string)
    else:
        # If function was not run_batch, write output
        if (function_name != 'run_batch'):
            WriteOutput(output_string)
        # Save loot filter if we called a mutator function
        if (kFunctionInfoMap[function_name]['ModifiesFilter']):
            loot_filter.SaveToFile()
# End DelegateFunctionCall

kUsageErrorString = ('ill-formed command-line call\n' +
  '  Check that the function name is spelled correctly and that the syntax is as follows:\n' +
  '  > python3 backend_cli.py <function_name> <function_arguments...> <profile_name (if required)>')

def main_impl():
    # Initialize log
    logger.InitializeLog(kLogFilename)
    argv_info_message: str = 'Info: sys.argv = ' + str(sys.argv)
    logger.Log(argv_info_message)
    # Check that there are enough params:
    #  - For non-profile-parameterized functions: script name, function name, ...
    #  - Otherwise: script name, function name, profile name, ...
    if (len(sys.argv) < 2):
        Error(kUsageErrorString)
    _, function_name, *remaining_args = sys.argv
    profile_name = None
    config_data = None
    if (kFunctionInfoMap[function_name]['HasProfileParam']):
        if (len(sys.argv) < 3):
            Error(kUsageErrorString)
        *function_params, profile_name = remaining_args
        if (not profile.ProfileExists(profile_name)):
            Error('profile "{}" does not exist'.format(profile_name))
        user_profile = profile.Profile(profile_name)
        config_data = user_profile.config_values
    else:  # function does not have Profile param
        function_params = remaining_args
    # If importing downloaded filter, first verify that downloaded filter exists,
    # then copy filter to input path.  Note: we wait to delete downloaded filter
    # until the end, so that if any errors occurred during import, the downloaded
    # filter will still be present (so that the user can then re-import).
    if (function_name == 'import_downloaded_filter'):
        if (os.path.isfile(config_data['DownloadedLootFilterFullpath'])):
            file_manip.CopyFile(config_data['DownloadedLootFilterFullpath'],
                                config_data['InputLootFilterFullpath'])
        else:
            Error('downloaded loot filter: "{}" does not exist'.format(
                    config_data['DownloadedLootFilterFullpath']))
    # Input filter is read from the output filter path, unless importing downloaded filter
    output_as_input_filter: bool = (function_name != 'import_downloaded_filter')
    # Delegate function call
    # Note: we create the loot filter first and pass in as a parameter,
    # so that in case of a batch, DelegateFunctionCall can call itself recursively
    loot_filter = LootFilter(profile_name, output_as_input_filter) if profile_name else None
    DelegateFunctionCall(loot_filter, function_name, function_params)
    # Check if we are importing and need to delete the downloaded filter
    if ((function_name == 'import_downloaded_filter') and config_data['RemoveDownloadedFilter']):
        file_manip.RemoveFileIfExists(config_data['DownloadedLootFilterFullpath'])
# End main  _impl

import time

# Wrap the main_impl in a try-except block, so we can detect any error
# and notify the frontend via backend_cli.exit_code
def main():
    helper.WriteToFile('-1', kExitCodeFilename)  # -1 = In-progress exit code
    try:
        main_impl()
    except Exception as e:
        traceback_message = traceback.format_exc()
        logger.Log(traceback_message)
        helper.WriteToFile('1', kExitCodeFilename)  # 1 = Generic error exit code
        raise e
    helper.WriteToFile('0', kExitCodeFilename)  # 0 = Success exit code

if (__name__ == '__main__'):
    main()
