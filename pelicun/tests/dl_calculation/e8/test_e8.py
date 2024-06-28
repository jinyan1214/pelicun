"""
DL Calculation Example 8

"""

import tempfile
import os
import shutil
from glob import glob
from pathlib import Path
import pytest
from pelicun.warnings import PelicunWarning
from pelicun.tools.DL_calculation import run_pelicun


# pylint: disable=missing-function-docstring
# pylint: disable=missing-yield-doc
# pylint: disable=missing-yield-type-doc
# pylint: disable=redefined-outer-name


@pytest.fixture
def obtain_temp_dir():

    # get the path of this file
    this_file = __file__

    initial_dir = os.getcwd()
    this_dir = str(Path(this_file).parent)

    temp_dir = tempfile.mkdtemp()

    yield this_dir, temp_dir

    # go back to the right directory, otherwise any tests that follow
    # could have issues.
    os.chdir(initial_dir)


def test_dl_calculation_8(obtain_temp_dir):

    this_dir, temp_dir = obtain_temp_dir

    # Copy all input files to a temporary directory.
    # All outputs will also go there.
    # This approach is more robust to changes in the output files over
    # time.

    ruleset_files = [
        Path(x).resolve()
        for x in glob('pelicun/tests/dl_calculation/rulesets/*Rulesets.py')
    ]

    os.chdir(this_dir)
    temp_dir = tempfile.mkdtemp()
    # copy input files
    for file_name in ('1-AIM.json', 'response.csv', 'auto_HU_LA.py'):
        shutil.copy(f'{this_dir}/{file_name}', f'{temp_dir}/{file_name}')

    # copy ruleset files
    for file_path in ruleset_files:
        shutil.copy(str(file_path), f'{temp_dir}/{file_path.name}')

    # change directory to there
    os.chdir(temp_dir)

    # run
    with pytest.warns(PelicunWarning):
        return_int = run_pelicun(
            demand_file='response.csv',
            config_path='1-AIM.json',
            output_path=None,
            coupled_EDP=True,
            realizations='100',
            auto_script_path='auto_HU_LA.py',
            detailed_results=False,
            regional=True,
            output_format=None,
            custom_model_dir=None,
            color_warnings=False,
        )

    assert return_int == 0

    # now remove the ruleset files and auto script
    for file_path in ruleset_files:
        os.remove(f'{temp_dir}/{file_path.name}')
    os.remove('auto_HU_LA.py')

    #
    # Test files
    #

    # Ensure the number of files is as expected
    num_files = sum(1 for entry in Path(temp_dir).iterdir() if entry.is_file())
    assert num_files == 19

    # Verify their names
    files = {
        '1-AIM.json',
        '1-AIM_ap.json',
        'CMP_QNT.csv',
        'CMP_sample.json',
        'DEM_sample.json',
        'DL_summary.csv',
        'DL_summary.json',
        'DL_summary_stats.csv',
        'DL_summary_stats.json',
        'DMG_grp.json',
        'DMG_grp_stats.json',
        'DV_repair_agg.json',
        'DV_repair_agg_stats.json',
        'DV_repair_grp.json',
        'DV_repair_sample.json',
        'DV_repair_stats.json',
        'pelicun_log.txt',
        'pelicun_log_warnings.txt',
        'response.csv',
    }

    for file in files:
        assert Path(f'{temp_dir}/{file}').is_file()

    #
    # Check the values in result files: TODO
    #
