#!/usr/bin/env python3
"""Execute the patched driver's actual mixer/gain functions against the observed graph.

Usage: python3 tools/test_audio_microphone_patch.py /path/to/patched/VoodooHDA
No Apple kernel headers are needed. The kext must also be compiled with its SDK.
"""
from pathlib import Path
import os
import shutil
import subprocess
import sys
import tempfile


def function(source, signature):
    """Extract one actual C++ definition, retaining its original function body."""
    start = source.index(signature)
    opening = source.index('{', start)
    depth = 1
    end = opening + 1
    while depth:
        if source[end] == '{':
            depth += 1
        elif source[end] == '}':
            depth -= 1
        end += 1
    return source[start:end]


STUBS = r'''
#include <cassert>
#include <cstdint>
#include <cstdio>
#include <set>
#include <vector>
using UInt32 = uint32_t;
using UInt64 = uint64_t;
using SInt32 = int32_t;
using SInt64 = int64_t;
using IOFixed = int32_t;
using IOReturn = int;
constexpr int kIOReturnSuccess = 0;
constexpr int kIOAudioStreamDirectionOutput = 0;
constexpr int kIOAudioStreamDirectionInput = 1;
constexpr int SOUND_MIXER_NRDEVICES = 25;
constexpr int SOUND_MIXER_VOLUME=0, SOUND_MIXER_PCM=4, SOUND_MIXER_LINE=6;
constexpr int SOUND_MIXER_MIC=7, SOUND_MIXER_IMIX=9, SOUND_MIXER_RECLEV=11;
constexpr int SOUND_MIXER_OGAIN=13, SOUND_MIXER_MONITOR=24;
constexpr UInt32 SOUND_MASK_VOLUME=1U<<0, SOUND_MASK_PCM=1U<<4;
constexpr UInt32 SOUND_MASK_LINE=1U<<6, SOUND_MASK_IMIX=1U<<9;
constexpr UInt32 SOUND_MASK_RECLEV=1U<<11, SOUND_MASK_MONITOR=1U<<24;
constexpr UInt32 SOUND_MASK_INPUT = (1U<<6)|(1U<<7)|(1U<<24);
constexpr int HDA_CTL_IN=2, HDA_CTL_OUT=1;
constexpr UInt32 HDA_AMP_MUTE_LEFT=1, HDA_AMP_MUTE_RIGHT=2;
constexpr int HDA_PARAM_AUDIO_WIDGET_CAP_TYPE_PIN_COMPLEX=4;
constexpr UInt32 HDAC_INVALID=~0U;
constexpr UInt32 HDA_CMD_SET_EAPD_BTL_ENABLE_EAPD=2;
constexpr UInt32 HDA_QUIRK_EAPDINV=1;
#define HDA_CMD_SET_EAPD_BTL_ENABLE(cad,nid,val) (0)
#define CODEC_ID(codec) ((UInt32(codec->vendorId)<<16)|codec->deviceId)
#define LOCK() ((void)0)
#define UNLOCK() ((void)0)
struct Codec { UInt32 vendorId=0x10ec, deviceId=0x0257, cad=0; };
struct Widget {
    int nid=0, bindAssoc=0, enable=1, type=0;
    struct { UInt32 eapdBtl=HDAC_INVALID; } params;
};
struct AudioControl {
    Widget *widget=nullptr;
    int enable=1, index=0, dir=HDA_CTL_IN, mute=0, step=0, size=0, offset=0;
    int left=-1, right=-1;
    UInt32 ossmask=0, muted=0;
};
struct FunctionGroup {
    Codec *codec=nullptr;
    int startNode=0, endNode=0;
    struct { UInt32 quirks=0; struct { bool digital=false; } assocs[2]; } audio;
    std::vector<AudioControl*> controls;
};
struct PcmDevice {
    FunctionGroup *funcGroup=nullptr;
    int playChanId=1, recChanId=0;
    UInt32 left[25]={}, right[25]={};
};
struct Channel {
    PcmDevice *pcmDevice=nullptr;
    FunctionGroup *funcGroup=nullptr;
    int assocNum=0;
};
struct IOAudioControl { int channel=1; int getChannelID() { return channel; } };
struct VoodooHDADevice {
    UInt32 mDeviceId=0x9dc88086U;
    Channel mChannels[2]; int mNumChannels=2;
    bool mEnableS540InputGainFix=true, mEnableVolumeChangeFix=true;
    bool mEnableHalfVolumeFix=false, mEnableHalfMicVolumeFix=false;
    UInt32 mMixerDefaults[25]={}; bool active=false;
    std::vector<UInt32> calls;
    void setProperty(const char*,bool value) { active=value; }
    AudioControl *audioCtlEach(FunctionGroup *fg, int i) {
        return i < int(fg->controls.size()) ? fg->controls[i] : nullptr;
    }
    Widget *widgetGet(FunctionGroup*,int) { return nullptr; }
    void sendCommand(int,int) {}
    void audioCtlAmpSet(AudioControl *ctl, UInt32 mute, int left, int right) {
        ctl->muted=mute; ctl->left=left; ctl->right=right;
    }
    UInt32 audioCtlOssMixerSetRecSrc(PcmDevice*,UInt32) { return 0; }
    bool s540InputGainFixEnabled(PcmDevice*);
    int audioCtlOssMixerSet(PcmDevice*,UInt32,UInt32,UInt32);
    int ilerp(int,int,float);
    void mixerSetDefaults(PcmDevice*);
    void mixerResume(PcmDevice*);
};
struct VoodooHDAEngine {
    Channel *mChannel=nullptr; VoodooHDADevice *mDevice=nullptr;
    bool mEnableS540InputGainFix=true, mEnableVolumeChangeFix=true, mEnableMuteFix=false;
    UInt32 oldInputGain=50, oldOutVolumeLeft=100, oldOutVolumeRight=100;
    int direction=kIOAudioStreamDirectionInput; int mVerbose=0;
    int getEngineDirection() { return direction; }
    void errorMsg(const char*,...) {}
    UInt64 getMinMaxDb(UInt32);
    IOReturn volumeChanged(IOAudioControl*,SInt32,SInt32);
    IOReturn muteChanged(IOAudioControl*,SInt32,SInt32);
};
'''

TESTS = r'''
int main() {
    Codec codec; FunctionGroup fg; fg.codec=&codec;
    Widget adcWidget, internalWidget, jackWidget, selectorWidget, dacWidget, speakerWidget;
    adcWidget.nid=8; internalWidget.nid=18; jackWidget.nid=25; selectorWidget.nid=35;
    dacWidget.nid=2; dacWidget.bindAssoc=1; speakerWidget.nid=20; speakerWidget.bindAssoc=1;
    AudioControl adc, internal, jack, selector, jackSelector, dac, speaker;
    adc.widget=&adcWidget; adc.mute=1; adc.step=63; adc.size=2; adc.offset=23;
    adc.ossmask=SOUND_MASK_IMIX|SOUND_MASK_RECLEV;
    internal.widget=&internalWidget; internal.step=3; internal.size=39;
    internal.ossmask=SOUND_MASK_MONITOR;
    jack.widget=&jackWidget; jack.step=3; jack.size=39; jack.ossmask=SOUND_MASK_LINE;
    selector.widget=&selectorWidget; selector.mute=1;
    selector.ossmask=SOUND_MASK_RECLEV|SOUND_MASK_MONITOR;
    jackSelector.widget=&selectorWidget; jackSelector.mute=1; jackSelector.index=1;
    jackSelector.ossmask=SOUND_MASK_RECLEV|SOUND_MASK_LINE;
    dac.widget=&dacWidget; dac.dir=HDA_CTL_OUT; dac.step=87; dac.size=2; dac.offset=87;
    dac.ossmask=SOUND_MASK_PCM;
    speaker.widget=&speakerWidget; speaker.dir=HDA_CTL_OUT; speaker.mute=1;
    speaker.ossmask=SOUND_MASK_VOLUME|SOUND_MASK_PCM;
    fg.controls={&adc,&internal,&jack,&selector,&jackSelector,&dac,&speaker};
    PcmDevice pcm; pcm.funcGroup=&fg;
    VoodooHDADevice device;
    device.mChannels[0]={&pcm,&fg,0}; device.mChannels[1]={&pcm,&fg,1};
    for(int n=0;n<25;n++) device.mMixerDefaults[n]=95;

    assert(device.s540InputGainFixEnabled(&pcm) && device.active);
    device.mEnableS540InputGainFix=false; assert(!device.s540InputGainFixEnabled(&pcm));
    device.mEnableS540InputGainFix=true;
    device.mDeviceId=0x12348086; assert(!device.s540InputGainFixEnabled(&pcm));
    device.mDeviceId=0x9dc88086;
    codec.deviceId=0x0256; assert(!device.s540InputGainFixEnabled(&pcm)); codec.deviceId=0x0257;
    internal.size=38; assert(!device.s540InputGainFixEnabled(&pcm)); internal.size=39;
    adc.offset=22; assert(!device.s540InputGainFixEnabled(&pcm)); adc.offset=23;
    adc.enable=0; assert(!device.s540InputGainFixEnabled(&pcm)); adc.enable=1;
    AudioControl unexpected=adc; Widget extra; extra.nid=9; unexpected.widget=&extra;
    fg.controls.push_back(&unexpected); assert(!device.s540InputGainFixEnabled(&pcm));
    fg.controls.pop_back(); assert(device.s540InputGainFixEnabled(&pcm));
    pcm.recChanId=2; assert(!device.s540InputGainFixEnabled(&pcm)); pcm.recChanId=0;

    device.mixerSetDefaults(&pcm);
    assert(pcm.left[SOUND_MIXER_RECLEV]==50);
    assert(pcm.left[SOUND_MIXER_IMIX]==100);
    assert(pcm.left[SOUND_MIXER_MONITOR]==100);
    assert(pcm.left[SOUND_MIXER_LINE]==100);
    assert(adc.left==32 && internal.left==0 && jack.left==0 && !selector.muted);

    VoodooHDAEngine input; input.mDevice=&device; input.mChannel=&device.mChannels[0];
    VoodooHDAEngine output; output.mDevice=&device; output.mChannel=&device.mChannels[1];
    output.direction=kIOAudioStreamDirectionOutput;
    IOAudioControl control;
    UInt64 range=input.getMinMaxDb(SOUND_MASK_RECLEV);
    assert(int32_t(range>>32)==-1130496); // -17.25 dB, signed 16.16
    assert(int32_t(range)==1966080); // +30.00 dB
    std::set<int> steps;
    int previous=-1;
    const int originalSpeakerGain=dac.left;
    for(int value=0;value<=100;value++) {
        input.volumeChanged(&control,0,value);
        assert(pcm.left[SOUND_MIXER_RECLEV]==UInt32(value));
        assert(adc.left==(value*63+50)/100 && adc.right==adc.left);
        assert(adc.left>=previous); previous=adc.left; steps.insert(adc.left);
        assert(internal.left==0 && jack.left==0 && dac.left==originalSpeakerGain);
        assert(pcm.left[SOUND_MIXER_IMIX]==100 && pcm.left[SOUND_MIXER_MONITOR]==100);
        assert(selector.muted==(value ? 0U : 3U));
    }
    assert(steps.size()==64 && *steps.begin()==0 && *steps.rbegin()==63);
    input.volumeChanged(&control,100,57);
    const int recordingGain=adc.left;
    for(int value=0;value<=100;value++) {
        output.volumeChanged(&control,0,value);
        assert(adc.left==recordingGain && internal.left==0 && jack.left==0);
        assert(pcm.left[SOUND_MIXER_RECLEV]==57 && pcm.left[SOUND_MIXER_MONITOR]==100);
    }
    output.muteChanged(&control,0,1); assert(pcm.left[SOUND_MIXER_PCM]==0);
    output.muteChanged(&control,1,0); assert(pcm.left[SOUND_MIXER_PCM]==100);
    assert(pcm.left[SOUND_MIXER_VOLUME]==95 && adc.left==recordingGain);
    input.muteChanged(&control,0,1); assert(adc.muted==3 && selector.muted==3);
    input.muteChanged(&control,1,0); assert(adc.left==recordingGain && adc.muted==0);
    assert(pcm.left[SOUND_MIXER_RECLEV]==57);

    // External panel attempts cannot reintroduce the multiplying routing factors.
    device.audioCtlOssMixerSet(&pcm,SOUND_MIXER_IMIX,30,30);
    device.audioCtlOssMixerSet(&pcm,SOUND_MIXER_MONITOR,70,70);
    device.audioCtlOssMixerSet(&pcm,SOUND_MIXER_LINE,0,0);
    assert(adc.left==recordingGain && internal.left==0 && jack.left==0);
    assert(selector.muted==0 && jackSelector.muted==0);
    device.mixerResume(&pcm);
    assert(adc.left==recordingGain && internal.left==0 && jack.left==0);
    assert(pcm.left[SOUND_MIXER_RECLEV]==57 && !adc.muted && !selector.muted);

    // The opt-in off path retains the upstream all-mixer volume behavior.
    device.mEnableS540InputGainFix=false; input.mEnableS540InputGainFix=false;
    input.volumeChanged(&control,57,30);
    for(int n=0;n<25;n++) assert(pcm.left[n]==30 && pcm.right[n]==30);
    assert(internal.left==1 && adc.left==6);
    std::puts("PASS: graph guards, 64 gain steps, precise dB, input/output isolation, mute and resume");
}
'''


def main():
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    source = Path(sys.argv[1]) / 'tranc'
    engine = (source / 'VoodooHDAEngine.cpp').read_text()
    device = (source / 'VoodooHDADevice.cpp').read_text()
    functions = [function(device, signature) for signature in (
        'bool VoodooHDADevice::s540InputGainFixEnabled(',
        'int VoodooHDADevice::audioCtlOssMixerSet(',
        'int VoodooHDADevice::ilerp(',
        'void VoodooHDADevice::mixerSetDefaults(',
        'void VoodooHDADevice::mixerResume(',
    )]
    functions += [function(engine, signature) for signature in (
        'UInt64 VoodooHDAEngine::getMinMaxDb(',
        'IOReturn VoodooHDAEngine::volumeChanged(',
        'IOReturn VoodooHDAEngine::muteChanged(',
    )]
    compiler = os.environ.get('CXX') or shutil.which('clang++') or shutil.which('g++')
    if not compiler:
        raise SystemExit('A C++ compiler is required')
    with tempfile.TemporaryDirectory(prefix='s540-audio-policy-') as temporary:
        cpp = Path(temporary) / 'policy.cpp'
        exe = Path(temporary) / 'policy-test'
        cpp.write_text(STUBS + '\n\n'.join(functions) + TESTS)
        subprocess.run([compiler, '-std=c++14', '-Wall', '-Wextra',
                        '-Wno-unused-parameter', '-Wno-unused-variable',
                        '-fsanitize=undefined,address', '-fno-omit-frame-pointer',
                        str(cpp), '-o', str(exe)], check=True)
        environment = dict(os.environ)
        # LeakSanitizer cannot inspect /proc in the managed Linux executor.
        # Address and undefined-behavior checks remain active.
        environment['ASAN_OPTIONS'] = 'detect_leaks=0:halt_on_error=1'
        environment['UBSAN_OPTIONS'] = 'halt_on_error=1:print_stacktrace=1'
        subprocess.run([str(exe)], env=environment, check=True)


if __name__ == '__main__':
    main()
