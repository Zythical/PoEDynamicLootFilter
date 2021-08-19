'''
This file defines the command-line interface for the AHK frontend
to call the Python backend.  The general call format is:

 > python3 backend_cli.py <function_name> <function_parameters>

Return values of functions will be placed in the file "backend_cli.output",
formatted as specified by the frontend developer.  (Note: make sure
calls to the cli are synchronous if return values are to be used,
so you ensure data is written before you try to read it.)

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
'''

import shlex
import sys
import traceback
from typing import List

import config
import consts
import helper
import logger
from loot_filter import RuleVisibility, LootFilterRule, LootFilter
from type_checker import CheckType

kLogFilename = 'backend_cli.log'
kInputFilename = 'backend_cli.input'
kOutputFilename = 'backend_cli.output'

# List of functions that modify the filter in any way
# This list excludes getter-only functions, which can be excluded from the profile data
kFilterMutatorFunctionNames = ['run_batch', 'set_currency_tier', 'adjust_currency_tier',
        'set_currency_tier_visibility', 'set_hide_currency_above_tier', 
        'set_hide_map_below_tier', 'set_chaos_recipe_enabled_for']

def CheckNumParams(params_list: List[str], required_num_params: int):
    CheckType(params_list, 'params_list', list)
    CheckType(required_num_params, 'required_num_params', int)
    if (len(params_list) != required_num_params):
        error_message: str = ('incorrect number of parameters given for '
                              'function {}: required {}, got {}').format(
                                   sys.argv[1], required_num_params, len(params_list))
        logger.Log('Error: ' + error_message)
        raise RuntimeError(error_message)
# End CheckNumParams

def ReadInput() -> List[str]:
    with open(kInputFilename) as input_file:
        return input_file.readlines()
# End ReadInput

def WriteOutput(output_string: str):
    CheckType(output_string, 'output_string', str)
    with open(kOutputFilename, 'w') as output_file:
        output_file.write(output_string)
# End WriteOutput

# function_output_string should be the whole string containing the given function call's output
def AppendFunctionOutput(function_output_string: str):
    CheckType(function_output_string, 'function_output_string', str)
    if ((len(function_output_string) == 0) or (function_output_string[-1] != '\n')):
        function_output_string += '\n'
    with open(kOutputFilename, 'a') as output_file:
        output_file.write(function_output_string + '@\n')
# End AppendFunctionOutput

# Passing in None as the loot filter here indicates to create the loot filter object,
# perform the call, and write the output all within this delegation.
# Passing in a LootFilter object instead indicates that there will be multiple
# consecutive function calls, so this delegation should not construct a LootFilter,
# and it should append its output to the output file rather than overwriting it.
def DelegateFunctionCall(loot_filter: LootFilter or None,
                         function_name: str,
                         function_params: List[str],
                         in_batch: bool = False):
    CheckType(loot_filter, 'loot_filter', (LootFilter, type(None)))
    CheckType(function_name, 'function_name', str)
    CheckType(function_params, 'function_params_list', list)
    output_string = ''
    # Initialize loot_filter if not in_batch and not running import_downloaded_filter
    if ((not in_batch) and (function_name != 'import_downloaded_filter')):
        loot_filter = LootFilter(config.kPathOfExileLootFilterFullpath)
    if (function_name == 'import_downloaded_filter'):
        '''
        import_downloaded_filter
         - Reads the filter located in the downloads directory, applies all DLF
           custom changes to it, and saves the result in the Path Of Exile directory.
           See config.py to configure filter file paths and names.
         - Output: None
         - Example: > python3 backend_cli.py import_downloaded_filter
        '''
        CheckNumParams(function_params, 0)
        loot_filter = LootFilter(config.kDownloadedLootFilterFullpath)
        # TODO: once profile saving is implemented, apply all saved changes to filter here
        loot_filter.SaveToFile(config.kPathOfExileLootFilterFullpath)
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
        loot_filter = LootFilter(config.kPathOfExileLootFilterFullpath)
        WriteOutput('')  # clear the output file, since we will be appending output in batch
        function_call_list: List[str] = ReadInput()
        for function_call_string in function_call_list:
            # need different variable names here to not overwrite the existing ones
            _function_name, *_function_params = shlex.split(function_call_string)
            DelegateFunctionCall(loot_filter, _function_name, _function_params, True)
    elif (function_name == 'set_currency_tier'):
        '''
        set_currency_tier <currency_name: str> <tier: int>
         - Moves the given currency type to the specified tier
         - Output: None
         - Example: > python3 backend_cli.py set_currency_tier "Chromatic Orb" 5
        '''
        CheckNumParams(function_params, 2)
        currency_name: str = function_params[0]
        target_tier: int = int(function_params[1])
        loot_filter.SetCurrencyToTier(currency_name, target_tier)
    elif (function_name == 'adjust_currency_tier'):
        '''
        adjust_currency_tier <currency_name: str> <tier_delta: int>
         - Moves the given currency type by a relative tier_delta
         - Output: None
         - Example: > python3 backend_cli.py adjust_currency_tier "Chromatic Orb" -2
        '''
        CheckNumParams(function_params, 2)
        currency_name: str = function_params[0]
        tier_delta: int = int(function_params[1])
        loot_filter.AdjustTierOfCurrency(currency_name, tier_delta)
    elif (function_name == 'get_all_currency_tiers'):
        '''
        get_all_currency_tiers
         - Output: newline-separated sequence of `<currency_name: str>;<tier: int>`,
           one per currency type
         - Example: > python3 backend_cli.py get_all_currency_tiers
        '''
        CheckNumParams(function_params, 0)
        output_string = ''
        for tier in consts.kCurrencyTierNames:
            currency_names = loot_filter.GetAllCurrencyInTier(tier)
            output_string += ''.join((currency_name + ';' + str(tier) + '\n')
                                        for currency_name in currency_names)
    elif (function_name == 'set_currency_tier_visibility'):
        '''
        set_currency_tier_visibility <tier: int or tier_tag: str> <visible_flag: int>
         - Sets the visibility for the given currency tier
         - First parameter may be a tier integer [1-9] or a tier tag string, such as:
           "tportal" for Portal Scrolls, "twisdom" for Wisdom Scrolls
         - visible_flag is 1 for True (enable), 0 for False (disable)
         - Output: None
         - Example: > python3 backend_cli.py set_currency_tier_visibility tportal 1
        '''
        CheckNumParams(function_params, 2)
        tier = function_params[0]
        if (tier.isdigit()): tier = int(tier)
        visible_flag = bool(int(function_params[1]))
        visibility = RuleVisibility.kShow if visible_flag else RuleVisibility.kHide
        loot_filter.SetCurrencyTierVisibility(tier, visibility)
    elif (function_name == 'get_currency_tier_visibility'):
        '''
        get_currency_tier_visibility <tier: int or tier_tag: str>
         - Parameter may be a tier integer [1-9] or a tier tag string, such as:
           "tportal" for Portal Scrolls, "twisdom" for Wisdom Scrolls
         - Output: "1" if the given currency tier is shown, "0" otherwise
         - Example: > python3 backend_cli.py get_currency_tier_visibility twisdom
        '''
        CheckNumParams(function_params, 1)
        tier = function_params[0]
        if (tier.isdigit()): tier = int(tier)
        output_string = str(int(loot_filter.GetCurrencyTierVisibility(tier) == RuleVisibility.kShow))
    elif (function_name == 'set_hide_currency_above_tier'):
        '''
        set_hide_currency_above_tier <tier: int>
         - Sets the currency tier "above" which all will be hidden (higher currency tiers are worse)
         - Output: None
         - Example: > python3 backend_cli.py set_hide_currency_above_tier 8
        '''
        CheckNumParams(function_params, 1)
        max_visible_tier: int = int(function_params[0])
        loot_filter.SetHideCurrencyAboveTierTier(max_visible_tier)
    elif (function_name == 'get_hide_currency_above_tier'):
        '''
        get_hide_currency_above_tier
         - Output: single integer, the tier above which all currency is hidden
         - Example: > python3 backend_cli.py get_hide_currency_above_tier
        '''
        CheckNumParams(function_params, 0)
        output_string = str(loot_filter.GetHideCurrencyAboveTierTier())
    elif (function_name == 'set_hide_map_below_tier'):
        '''
        set_hide_map_below_tier <tier: int>
         - Sets the map tier below which all will be hidden (use 0/1 to show all)
         - Output: None
         - Example: > python3 backend_cli.py set_hide_map_below_tier 14
        '''
        min_visibile_tier: int = int(function_params[0])
        loot_filter.SetHideMapsBelowTierTier(min_visibile_tier)
    elif (function_name == 'get_hide_map_below_tier'):
        '''
        get_hide_map_below_tier
         - Output:  single integer, the tier below which all maps are hidden
         - Example: > python3 backend_cli.py get_hide_map_below_tier
        '''
        output_string = str(loot_filter.GetHideMapsBelowTierTier())
    elif (function_name == 'set_chaos_recipe_enabled_for'):
        '''
        set_chaos_recipe_enabled_for <item_slot: str> <enable_flag: int>
         - <item_slot> is one of: "Weapons", "Body Armours", "Helmets", "Gloves",
           "Boots", "Amulets", "Rings", "Belts"
         - enable_flag is 1 for True (enable), 0 for False (disable)
         - Output: None
         - Example: > python3 backend_cli.py set_chaos_recipe_enabled_for Weapons 0
        '''
        item_slot: str = function_params[0]
        enable_flag: bool = bool(int(function_params[1]))
        loot_filter.SetChaosRecipeEnabledFor(item_slot, enable_flag)
    elif (function_name == 'is_chaos_recipe_enabled_for'):
        '''
        is_chaos_recipe_enabled_for <item_slot: str>
         - <item_slot> is one of: "Weapons", "Body Armours", "Helmets", "Gloves",
           "Boots", "Amulets", "Rings", "Belts"
         - Output: "1" if chaos recipe items are showing for the given item_slot, else "0"
         - Example: > python3 backend_cli.py is_chaos_recipe_enabled_for "Body Armours"
        '''
        item_slot: str = function_params[0]
        output_string = str(int(loot_filter.IsChaosRecipeEnabledFor(item_slot)))
    elif (function_name == 'get_all_chaos_recipe_statuses'):
        '''
        get_all_chaos_recipe_statuses
         - Output: one line formatted as `<item_slot>;<enabled_flag>` for each item slot
         - <item_slot> is one of: "Weapons", "Body Armours", "Helmets", "Gloves",
           "Boots", "Amulets", "Rings", "Belts"
         - <enabled_flag> is "1" if chaos recipe items are showing for the given item_slot, else "0"
         - Example: > python3 backend_cli.py get_all_chaos_recipe_statuses
        '''
        for item_slot in consts.kChaosRecipeItemSlots:
            enabled_flag_string = str(int(loot_filter.IsChaosRecipeEnabledFor(item_slot)))
            output_string += item_slot + ';' + enabled_flag_string + '\n'
    else:
        error_message: str = 'Function "{}" not found'.format(function_name)
        logger.Log('Error: ' + error_message)
        raise RuntimeError(error_message)
    # Function call delegation completed, and return value is in output_string
    # If we just ran a single function, we can write the output to the output file,
    # but if we are in a batch we have to append to avoid overwriting on consecutive calls
    if (in_batch):
        AppendFunctionOutput(output_string)
    else:
        # Save loot filter if not in batch, and called a mutator function
        if (function_name in kFilterMutatorFunctionNames):
            loot_filter.SaveToFile(config.kPathOfExileLootFilterFullpath)
        # Write output, unless this function is run_batch, in which case output is already appended
        if (function_name != 'run_batch'):
            WriteOutput(output_string)
# End DelegateFunctionCall
        
def main():
    # Initialize
    logger.InitializeLog(kLogFilename)
    argv_info_message: str = 'Info: sys.argv = ' + str(sys.argv)
    print(argv_info_message)
    logger.Log(argv_info_message)
    # Check that there at least exists a function name in argv
    if (len(sys.argv) < 2):
        error_message: str = 'no function specified, too few command line arguments given'
        logger.Log('Error: ' + error_message)
        raise RuntimeError(error_message)
    # Delegate function call based on name
    function_name: str = sys.argv[1]
    try:
        DelegateFunctionCall(None, function_name, sys.argv[2:])
    except Exception as e:
        traceback_message = traceback.format_exc()
        logger.Log(traceback_message)
        raise e
# End main    

if (__name__ == '__main__'):
    main()
