#!/usr/bin/env python3
"""Isolated manual retained first-initialization frontend; old idle ABI frozen."""
from pathlib import Path
import hashlib

HERE=Path(__file__).resolve().parent
DIRECTORY='packages/nvidia-gsp-bootstrap/prospective-experimental-target-control'
KMOD='packages/nvidia-gsp-bootstrap/prospective-loader/S540ProspectiveLoaderKmod.cpp'
OLD_KERNEL='packages/nvidia-gsp-bootstrap/prospective-loader/S540ProspectiveLoaderKernel.cpp'
INPUTS=(KMOD,)
ORIGINAL_INPUTS=()
RETIRED_PROJECT_UNITS=(OLD_KERNEL,)
BASE_SHA256={KMOD:'33e8371b7a5880515ba6625f642ccefd2c593463aa4c91fd1f3ce87f4c2e7052'}
NAMES=('S540ExperimentalTargetProtocol.h','S540ExperimentalTargetState.h',
    'S540ExperimentalTargetState.c','S540ExperimentalTargetKernel.hpp','S540ExperimentalTargetKernel.cpp',
    'experimental_ctl.c','tests/sdk_experimental_metaclass_reference.cpp',
    'tests/sdk_experimental_operations_reference.cpp','tests/sdk_experimental_protocol_reference.c')
COMPANIONS={DIRECTORY+'/'+name:HERE/name for name in NAMES}
PROJECT_UNITS=({'source':DIRECTORY+'/S540ExperimentalTargetState.c','kind':'plain-c'},
               {'source':DIRECTORY+'/S540ExperimentalTargetKernel.cpp','kind':'cpp'})
INCLUDE_DIRECTORIES=(DIRECTORY,)
COMPILE_DEFINITIONS={}
EXPORTS={DIRECTORY+'/S540ExperimentalTargetState.c':(
    's540ExperimentalModuleEnter','s540ExperimentalServiceStart','s540ExperimentalRequestBegin',
    's540ExperimentalRequestFinish','s540ExperimentalRequestStop','s540ExperimentalServiceGone'),
    DIRECTORY+'/S540ExperimentalTargetKernel.cpp':(
    's540ExperimentalModuleStartBackend','s540ExperimentalModuleStopBackend')}
SOURCE_FILES=('experimental_ctl.c','tests/sdk_experimental_metaclass_reference.cpp',
    'tests/sdk_experimental_operations_reference.cpp','tests/sdk_experimental_protocol_reference.c',
    'tests/check_state.c','check.py','SOURCE-CONTRACT.json')

def transforms(values):
    if set(values)!=set(INPUTS): raise ValueError('Exact experimental frontend input inventory required')
    text=values[KMOD]
    if hashlib.sha256(text.encode()).hexdigest()!=BASE_SHA256[KMOD]:
        raise ValueError('Reviewed old Kmod source changed')
    replacements={
        '#include "S540ProspectiveLoaderKernel.hpp"':'#include "S540ExperimentalTargetKernel.hpp"',
        's540ProspectiveModuleStartBackend(info)':'s540ExperimentalModuleStartBackend(info)',
        's540ProspectiveModuleStopBackend()':'s540ExperimentalModuleStopBackend()',
        'KMOD_EXPLICIT_DECL(org.osx86.S540ProspectiveLoader,':'KMOD_EXPLICIT_DECL(org.osx86.S540ExperimentalInit,'}
    for before,after in replacements.items():
        if text.count(before)!=1: raise ValueError('Experimental Kmod anchor absent/ambiguous: '+before)
        text=text.replace(before,after)
    return {KMOD:text}
