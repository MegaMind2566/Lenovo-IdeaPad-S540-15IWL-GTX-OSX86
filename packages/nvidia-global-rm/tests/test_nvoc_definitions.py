"""Actual Mach-O controls for the deliberately narrow definition binder."""
from pathlib import Path
import copy
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'builders'))
import nvidia_nvoc_definitions as proof

class ActualObjects(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cc=os.environ.get('S540_STACK_TEST_CLANG') or shutil.which('clang') or shutil.which('clang-18')
        cls.objdump=os.environ.get('S540_STACK_TEST_OBJDUMP') or shutil.which('llvm-objdump-18') or shutil.which('llvm-objdump')
        if not cls.cc:raise unittest.SkipTest('Actual Clang required.')
        if sys.platform=='darwin':
            cls.decoder=['/usr/bin/xcrun','otool','-tv']
        else:
            if not cls.objdump:raise unittest.SkipTest('Actual Mach-O disassembler required.')
            cls.decoder=[cls.objdump,'--macho','--disassemble','--no-show-raw-insn','--no-symbolic-operands']

    def assembly(self,directory,name,text):
        source=directory/(name+'.s');obj=source.with_suffix('.o');source.write_text(text)
        subprocess.run([self.cc,'-target','x86_64-apple-macos15','-c',str(source),'-o',str(obj)],
                       capture_output=True,text=True,check=True)
        return proof.macho.Object(obj)

    def initializer(self):
        external=' movq _target@GOTPCREL(%rip), %rdx\n movq %rdx, 264(%rdi)\n'
        local=' leaq _stub(%rip), %r8\n movq %r8, 264(%rdi)\n'
        return '.text\n.globl _init\n_init:\n'+external+local+external*3+' retq\n.p2align 4\n_stub:\n movl $86, %eax\n retq\n'

    def check_stores(self,image):
        instructions,_=proof.decode(image.path,self.decoder)
        return proof.initializer_stores(image,'_init',['_stub','_target'],264,instructions)

    def test_exact_actual_pointer_loads_stores_and_local_external_relocations(self):
        with tempfile.TemporaryDirectory() as directory:
            image=self.assembly(Path(directory),'init',self.initializer())
            _,rows=self.check_stores(image)
            self.assertEqual([r['kind'] for r in rows],[3,1,3,3,3])
            self.assertTrue(all(r['width']==4 and r['pc_relative'] for r in rows))

    def test_instruction_and_relocation_mutations_are_refused(self):
        replacements=[
            ('movq %rdx, 264(%rdi)','movl %edx, 264(%rdi)'),
            ('movq %rdx, 264(%rdi)','movq %rax, 264(%rdi)'),
            ('movq %rdx, 264(%rdi)','movq %rdx, 264(%rsi)'),
            ('movq %rdx, 264(%rdi)','movq %rdx, 272(%rdi)'),
            ('movq %rdx, 264(%rdi)','movq %rdx, 264(%rdi,%rax,1)'),
            ('movq %rdx, 264(%rdi)','nop\n movq %rdx, 264(%rdi)'),
            ('movq _target@GOTPCREL(%rip), %rdx','leaq _target(%rip), %rdx'),
            ('leaq _stub(%rip), %r8','leaq _stub+1(%rip), %r8'),
            ('movq %rdx, 264(%rdi)','movq %rdx, 264(%rdi)\n movq %rax, 264(%rdi)'),
            ('movq %rdx, 264(%rdi)','movq %rdx, 264(%rdi)\n movq %rax, 260(%rdi)'),
            ('movq _target@GOTPCREL(%rip), %rdx\n movq %rdx, 264(%rdi)\n',''),
        ]
        for index,(old,new) in enumerate(replacements):
            with self.subTest(index=index),tempfile.TemporaryDirectory() as directory:
                image=self.assembly(Path(directory),'bad',self.initializer().replace(old,new,1))
                with self.assertRaises(ValueError):self.check_stores(image)

    def test_target_reference_outside_initializer_is_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            image=self.assembly(Path(directory),'outside',self.initializer()+
                '\n.globl _other\n_other:\n movq _target@GOTPCREL(%rip), %rax\n retq\n')
            with self.assertRaisesRegex(ValueError,'outside'):self.check_stores(image)

    def test_same_local_name_does_not_replace_atom_or_relocation_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            directory=Path(directory)
            baseline=self.assembly(directory,'a','.text\n_stub:\n movl $86,%eax\n retq\n')
            changed=self.assembly(directory,'b','.text\n_stub:\n movl $87,%eax\n retq\n')
            proof.local_identity(baseline,baseline,'_stub')
            with self.assertRaisesRegex(ValueError,'differs'):proof.local_identity(baseline,changed,'_stub')
            a=self.assembly(directory,'c','.text\n_stub:\n callq _side_a\n retq\n')
            b=self.assembly(directory,'d','.text\n_stub:\n callq _side_b\n retq\n')
            self.assertEqual(proof.atom(a,'_stub',external=False)['bytes_sha256'],
                             proof.atom(b,'_stub',external=False)['bytes_sha256'])
            with self.assertRaisesRegex(ValueError,'relocations'):proof.local_identity(a,b,'_stub')

    def test_identically_named_weak_relocation_does_not_replace_strong_reference(self):
        with tempfile.TemporaryDirectory() as directory:
            directory=Path(directory)
            strong=self.assembly(directory,'strong','.text\n_stub:\n callq _side\n retq\n')
            weak=self.assembly(directory,'weak','.weak_reference _side\n.text\n_stub:\n callq _side\n retq\n')
            actual=proof.atom(strong,'_stub',external=False)
            candidate=proof.atom(weak,'_stub',external=False)
            self.assertEqual(actual['bytes_sha256'],candidate['bytes_sha256'])
            self.assertEqual(actual['relocations'][0]['target'],candidate['relocations'][0]['target'])
            self.assertNotEqual(actual['relocations'][0]['target_linkage'],candidate['relocations'][0]['target_linkage'])
            with self.assertRaisesRegex(ValueError,'relocations'):proof.local_identity(strong,weak,'_stub')

    def test_duplicate_weak_common_and_aliased_definitions_are_refused(self):
        variants={
            'strong':'.text\n.globl _target\n_target:\n retq\n',
            'weak':'.text\n.globl _target\n.weak_definition _target\n_target:\n retq\n',
            'common':'.text\n_stub:\n retq\n.comm _target,8,3\n',
            'alias':'.text\n.globl _target\n.globl _alias\n_target:\n_alias:\n retq\n',
        }
        with tempfile.TemporaryDirectory() as directory:
            directory=Path(directory);images={n:self.assembly(directory,n,s) for n,s in variants.items()}
            proof.unique_external([{'image':images['strong']}],'_target')
            for name in ('weak','common','alias'):
                with self.subTest(name=name),self.assertRaises(ValueError):proof.unique_external([{'image':images[name]}],'_target')
            with self.assertRaisesRegex(ValueError,'one exact definition'):
                proof.unique_external([{'image':images['strong']},{'image':images['strong']}],'_target')

    def captures(self,root):
        source=root/'source';source.mkdir();objects=root/'objects';objects.mkdir();references=[]
        for index in range(2):
            c=source/(str(index)+'.c');o=objects/(str(index)+'.o');c.write_text('int function'+str(index)+'(void) {return 1;}\n')
            command=[self.cc,'-target','x86_64-apple-macos15','-O2','-ffreestanding','-fstack-usage','-c',str(c),'-o',str(o)]
            subprocess.run(command,capture_output=True,text=True,check=True)
            references.append(proof.stack.capture_usage(c,o,command,cwd=root))
        manifest=objects/'manifest.json';proof.stack.usage_manifest(references,manifest)
        return manifest

    def test_manifest_binds_every_object_capture_source_and_actual_stack_file(self):
        with tempfile.TemporaryDirectory() as directory:
            manifest=self.captures(Path(directory))
            self.assertEqual(len(proof.load_manifest(manifest,proof.Paths(),expected_count=2)),2)
            (manifest.parent/'extra.o').write_bytes((manifest.parent/'0.o').read_bytes())
            with self.assertRaisesRegex(ValueError,'extra'):proof.load_manifest(manifest,proof.Paths(),expected_count=2)

    def test_repeated_capture_and_changed_source_are_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            manifest=self.captures(Path(directory));data=json.loads(manifest.read_text());original=copy.deepcopy(data)
            data['units'][1]=data['units'][0];manifest.write_text(json.dumps(data))
            with self.assertRaisesRegex(ValueError,'Repeated capture'):proof.load_manifest(manifest,proof.Paths(),expected_count=2)
            manifest.write_text(json.dumps(original));(Path(directory)/'source/1.c').write_text('int changed;\n')
            with self.assertRaisesRegex(ValueError,'hash changed'):proof.load_manifest(manifest,proof.Paths(),expected_count=2)

    def update_capture(self,manifest,index,mutate):
        data=json.loads(manifest.read_text());reference=data['units'][index]
        capture=Path(reference['path']);unit=json.loads(capture.read_text());mutate(unit)
        proof.stack.write(capture,unit);reference['sha256']=proof.stack.sha(capture)
        proof.stack.write(manifest,data)

    def test_rehashed_command_and_sidecar_mismatches_are_refused(self):
        def wrong_input(unit):unit['command'][unit['command'].index('-c')+1]=str(Path(unit['source']).with_name('1.c'))
        def wrong_output(unit):unit['command'][unit['command'].index('-o')+1]=str(Path(unit['object']).with_name('1.o'))
        def missing_measurement(unit):unit['command'].remove('-fstack-usage')
        def duplicate_output(unit):unit['command']+=['-o',unit['object']]
        def wrong_sidecar(unit):
            unit['usage_file']=str(Path(unit['usage_file']).with_name('1.su'))
            unit['usage_sha256']=proof.stack.sha(Path(unit['usage_file']))
        for mutate in (wrong_input,wrong_output,missing_measurement,duplicate_output,wrong_sidecar):
            with self.subTest(mutate=mutate.__name__),tempfile.TemporaryDirectory() as directory:
                manifest=self.captures(Path(directory))
                def rehash(unit):
                    mutate(unit)
                    unit['command_sha256']=proof.hashlib.sha256(json.dumps(unit['command']).encode()).hexdigest()
                self.update_capture(manifest,0,rehash)
                with self.assertRaises(ValueError):proof.load_manifest(manifest,proof.Paths(),expected_count=2)

    def test_rehashed_stack_record_requires_an_actual_text_definition(self):
        with tempfile.TemporaryDirectory() as directory:
            manifest=self.captures(Path(directory))
            def mutate(unit):
                sidecar=Path(unit['usage_file'])
                sidecar.write_text(sidecar.read_text().replace('function0','invented0'))
                unit['usage_sha256']=proof.stack.sha(sidecar)
                unit['functions']=proof.stack.parse_usage(sidecar.read_text())
                self.assertEqual(unit['functions'][0]['symbol'],'_invented0')
            self.update_capture(manifest,0,mutate)
            with self.assertRaisesRegex(ValueError,'actual text definition'):
                proof.load_manifest(manifest,proof.Paths(),expected_count=2)

    def test_rehashed_capture_with_different_sidecar_name_is_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            manifest=self.captures(Path(directory));data=json.loads(manifest.read_text())
            old=Path(data['units'][0]['path']);renamed=old.with_name('different.stack.json');old.rename(renamed)
            data['units'][0]['path']=str(renamed);proof.stack.write(manifest,data)
            with self.assertRaisesRegex(ValueError,'exact source and object'):
                proof.load_manifest(manifest,proof.Paths(),expected_count=2)

    def test_explicit_path_relocation_still_requires_recorded_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'source.c').write_text('int exact;\n')
            paths=proof.Paths([('/unavailable/original',root)])
            self.assertEqual(paths.checked_file('/unavailable/original/source.c',proof.stack.sha(root/'source.c')),(root/'source.c').resolve())
            with self.assertRaises(ValueError):paths.checked_file('/unavailable/original/source.c','0'*64)
            with self.assertRaises(FileNotFoundError):paths.path('/unavailable/original/missing.c')

if __name__=='__main__':unittest.main()
