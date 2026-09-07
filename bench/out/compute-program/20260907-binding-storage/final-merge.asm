
packages/doe-gpu-linux-x64/bin/libwebgpu_doe.so:     file format elf64-x86-64


Disassembly of section .init:

Disassembly of section .fini:

Disassembly of section .text:

000000000016dca0 <native.support.doe_native_command_types.tryMergeDispatchIntoLast>:
  16dca0:	48 85 f6             	test   %rsi,%rsi
  16dca3:	74 46                	je     16dceb <native.support.doe_native_command_types.tryMergeDispatchIntoLast+0x4b>
  16dca5:	80 ba 90 30 00 00 00 	cmpb   $0x0,0x3090(%rdx)
  16dcac:	75 3d                	jne    16dceb <native.support.doe_native_command_types.tryMergeDispatchIntoLast+0x4b>
  16dcae:	48 69 c6 a0 30 00 00 	imul   $0x30a0,%rsi,%rax
  16dcb5:	80 7c 07 f0 00       	cmpb   $0x0,-0x10(%rdi,%rax,1)
  16dcba:	75 2f                	jne    16dceb <native.support.doe_native_command_types.tryMergeDispatchIntoLast+0x4b>
  16dcbc:	48 01 c7             	add    %rax,%rdi
  16dcbf:	48 8b 87 90 f3 ff ff 	mov    -0xc70(%rdi),%rax
  16dcc6:	48 3b 82 30 24 00 00 	cmp    0x2430(%rdx),%rax
  16dccd:	75 1c                	jne    16dceb <native.support.doe_native_command_types.tryMergeDispatchIntoLast+0x4b>
  16dccf:	48 8b 87 98 f3 ff ff 	mov    -0xc68(%rdi),%rax
  16dcd6:	48 3b 82 38 24 00 00 	cmp    0x2438(%rdx),%rax
  16dcdd:	75 0c                	jne    16dceb <native.support.doe_native_command_types.tryMergeDispatchIntoLast+0x4b>
  16dcdf:	0f b6 47 e0          	movzbl -0x20(%rdi),%eax
  16dce3:	3a 82 80 30 00 00    	cmp    0x3080(%rdx),%al
  16dce9:	74 03                	je     16dcee <native.support.doe_native_command_types.tryMergeDispatchIntoLast+0x4e>
  16dceb:	31 c0                	xor    %eax,%eax
  16dced:	c3                   	ret
  16dcee:	55                   	push   %rbp
  16dcef:	48 89 e5             	mov    %rsp,%rbp
  16dcf2:	41 57                	push   %r15
  16dcf4:	41 56                	push   %r14
  16dcf6:	53                   	push   %rbx
  16dcf7:	50                   	push   %rax
  16dcf8:	8b 5f c0             	mov    -0x40(%rdi),%ebx
  16dcfb:	3b 9a 60 30 00 00    	cmp    0x3060(%rdx),%ebx
  16dd01:	0f 85 11 01 00 00    	jne    16de18 <native.support.doe_native_command_types.tryMergeDispatchIntoLast+0x178>
  16dd07:	8b 47 c4             	mov    -0x3c(%rdi),%eax
  16dd0a:	3b 82 64 30 00 00    	cmp    0x3064(%rdx),%eax
  16dd10:	0f 85 02 01 00 00    	jne    16de18 <native.support.doe_native_command_types.tryMergeDispatchIntoLast+0x178>
  16dd16:	8b 47 c8             	mov    -0x38(%rdi),%eax
  16dd19:	3b 82 68 30 00 00    	cmp    0x3068(%rdx),%eax
  16dd1f:	0f 85 f3 00 00 00    	jne    16de18 <native.support.doe_native_command_types.tryMergeDispatchIntoLast+0x178>
  16dd25:	8b 47 cc             	mov    -0x34(%rdi),%eax
  16dd28:	3b 82 6c 30 00 00    	cmp    0x306c(%rdx),%eax
  16dd2e:	0f 85 e4 00 00 00    	jne    16de18 <native.support.doe_native_command_types.tryMergeDispatchIntoLast+0x178>
  16dd34:	8b 47 d0             	mov    -0x30(%rdi),%eax
  16dd37:	3b 82 70 30 00 00    	cmp    0x3070(%rdx),%eax
  16dd3d:	0f 85 d5 00 00 00    	jne    16de18 <native.support.doe_native_command_types.tryMergeDispatchIntoLast+0x178>
  16dd43:	8b 47 d4             	mov    -0x2c(%rdi),%eax
  16dd46:	3b 82 74 30 00 00    	cmp    0x3074(%rdx),%eax
  16dd4c:	0f 85 c6 00 00 00    	jne    16de18 <native.support.doe_native_command_types.tryMergeDispatchIntoLast+0x178>
  16dd52:	8b 47 d8             	mov    -0x28(%rdi),%eax
  16dd55:	3b 82 78 30 00 00    	cmp    0x3078(%rdx),%eax
  16dd5b:	0f 85 b7 00 00 00    	jne    16de18 <native.support.doe_native_command_types.tryMergeDispatchIntoLast+0x178>
  16dd61:	48 8d 87 60 cf ff ff 	lea    -0x30a0(%rdi),%rax
  16dd68:	48 39 d0             	cmp    %rdx,%rax
  16dd6b:	74 2a                	je     16dd97 <native.support.doe_native_command_types.tryMergeDispatchIntoLast+0xf7>
  16dd6d:	c5 fa 6f 47 a0       	vmovdqu -0x60(%rdi),%xmm0
  16dd72:	c5 fa 6f 4f b0       	vmovdqu -0x50(%rdi),%xmm1
  16dd77:	62 f3 7d 08 3f 82 40 	vpcmpneqb 0x3040(%rdx),%xmm0,%k0
  16dd7e:	30 00 00 04 
  16dd82:	62 f3 75 08 3f 8a 50 	vpcmpneqb 0x3050(%rdx),%xmm1,%k1
  16dd89:	30 00 00 04 
  16dd8d:	c5 f8 98 c1          	kortestw %k1,%k0
  16dd91:	0f 85 81 00 00 00    	jne    16de18 <native.support.doe_native_command_types.tryMergeDispatchIntoLast+0x178>
  16dd97:	49 89 fe             	mov    %rdi,%r14
  16dd9a:	49 89 d7             	mov    %rdx,%r15
  16dd9d:	48 81 c7 a0 f3 ff ff 	add    $0xfffffffffffff3a0,%rdi
  16dda4:	48 81 c2 40 24 00 00 	add    $0x2440,%rdx
  16ddab:	48 89 de             	mov    %rbx,%rsi
  16ddae:	48 89 d9             	mov    %rbx,%rcx
  16ddb1:	e8 1a 26 02 00       	call   1903d0 <mem.eql__anon_47795>
  16ddb6:	a8 01                	test   $0x1,%al
  16ddb8:	74 5e                	je     16de18 <native.support.doe_native_command_types.tryMergeDispatchIntoLast+0x178>
  16ddba:	49 8d be a0 f7 ff ff 	lea    -0x860(%r14),%rdi
  16ddc1:	49 8d 97 40 28 00 00 	lea    0x2840(%r15),%rdx
  16ddc8:	48 89 de             	mov    %rbx,%rsi
  16ddcb:	48 89 d9             	mov    %rbx,%rcx
  16ddce:	e8 fd 25 02 00       	call   1903d0 <mem.eql__anon_47795>
  16ddd3:	a8 01                	test   $0x1,%al
  16ddd5:	74 41                	je     16de18 <native.support.doe_native_command_types.tryMergeDispatchIntoLast+0x178>
  16ddd7:	49 8d be a0 fb ff ff 	lea    -0x460(%r14),%rdi
  16ddde:	49 8d 97 40 2c 00 00 	lea    0x2c40(%r15),%rdx
  16dde5:	48 89 de             	mov    %rbx,%rsi
  16dde8:	48 89 d9             	mov    %rbx,%rcx
  16ddeb:	e8 e0 25 02 00       	call   1903d0 <mem.eql__anon_47795>
  16ddf0:	a8 01                	test   $0x1,%al
  16ddf2:	74 24                	je     16de18 <native.support.doe_native_command_types.tryMergeDispatchIntoLast+0x178>
  16ddf4:	41 8b 4e dc          	mov    -0x24(%r14),%ecx
  16ddf8:	41 8b 87 7c 30 00 00 	mov    0x307c(%r15),%eax
  16ddff:	83 f9 01             	cmp    $0x1,%ecx
  16de02:	83 d1 00             	adc    $0x0,%ecx
  16de05:	83 f8 01             	cmp    $0x1,%eax
  16de08:	83 d0 00             	adc    $0x0,%eax
  16de0b:	01 c8                	add    %ecx,%eax
  16de0d:	0f 92 c1             	setb   %cl
  16de10:	0f 92 45 e4          	setb   -0x1c(%rbp)
  16de14:	84 c9                	test   %cl,%cl
  16de16:	74 0d                	je     16de25 <native.support.doe_native_command_types.tryMergeDispatchIntoLast+0x185>
  16de18:	31 c0                	xor    %eax,%eax
  16de1a:	48 83 c4 08          	add    $0x8,%rsp
  16de1e:	5b                   	pop    %rbx
  16de1f:	41 5e                	pop    %r14
  16de21:	41 5f                	pop    %r15
  16de23:	5d                   	pop    %rbp
  16de24:	c3                   	ret
  16de25:	41 89 46 dc          	mov    %eax,-0x24(%r14)
  16de29:	b0 01                	mov    $0x1,%al
  16de2b:	eb ed                	jmp    16de1a <native.support.doe_native_command_types.tryMergeDispatchIntoLast+0x17a>

Disassembly of section .plt:
