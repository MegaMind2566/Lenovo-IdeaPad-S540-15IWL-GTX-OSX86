"""Canonical 104-byte native profile. It is experimental, not a stack proof."""
import re
import struct
FORMAT=struct.Struct('<II32s16sQQQQQQ')
RESERVES=(2048,4096,1024,1024)

def encode_profile(code_contract_sha256,worker_stack_bytes,irq_stack_bytes,target_build='25G241',
                   framework_allowance_bytes=2048,unknown_allowance_bytes=4096,
                   recursion_allowance_bytes=1024,exception_allowance_bytes=1024):
    if not isinstance(code_contract_sha256,str) or not re.fullmatch('[0-9a-f]{64}',code_contract_sha256) or int(code_contract_sha256,16)==0:
        raise ValueError('Actual nonzero native code contract required')
    if target_build!='25G241':raise ValueError('Exact reviewed target build required')
    numbers=(worker_stack_bytes,irq_stack_bytes,framework_allowance_bytes,unknown_allowance_bytes,
             recursion_allowance_bytes,exception_allowance_bytes)
    if any(type(x) is not int for x in numbers):raise ValueError('Integer profile bytes required')
    if any(not 8192<=x<=16384 for x in numbers[:2]) or numbers[2:]!=RESERVES:
        raise ValueError('Experimental capacity or explicit allowances changed')
    return FORMAT.pack(1,FORMAT.size,bytes.fromhex(code_contract_sha256),target_build.encode()+b'\0'*10,*numbers)

def decode_profile(data):
    if not isinstance(data,bytes) or len(data)!=FORMAT.size:raise ValueError('Exact104 byte profile required')
    version,size,digest,build,*numbers=FORMAT.unpack(data)
    try:target=build.rstrip(b'\0').decode('ascii')
    except UnicodeError as error:raise ValueError('Invalid target build bytes') from error
    value=dict(code_contract_sha256=digest.hex(),target_build=target,
        **dict(zip(('worker_stack_bytes','irq_stack_bytes','framework_allowance_bytes',
            'unknown_allowance_bytes','recursion_allowance_bytes','exception_allowance_bytes'),numbers)))
    if version!=1 or size!=FORMAT.size or encode_profile(**value)!=data:raise ValueError('Noncanonical native profile')
    return dict(format=version,bytes=size,**value)
