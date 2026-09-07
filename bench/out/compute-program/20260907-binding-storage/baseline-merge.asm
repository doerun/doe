
packages/doe-gpu-linux-x64/bin/libwebgpu_doe.so:     file format elf64-x86-64


Disassembly of section .init:

Disassembly of section .fini:

Disassembly of section .text:

000000000016dca0 <native.support.doe_native_command_types.tryMergeDispatchIntoLast>:
  16dca0:	55                   	push   %rbp
  16dca1:	48 89 e5             	mov    %rsp,%rbp
  16dca4:	41 57                	push   %r15
  16dca6:	41 56                	push   %r14
  16dca8:	41 55                	push   %r13
  16dcaa:	41 54                	push   %r12
  16dcac:	53                   	push   %rbx
  16dcad:	48 81 ec 98 30 00 00 	sub    $0x3098,%rsp
  16dcb4:	4c 8b 6f 08          	mov    0x8(%rdi),%r13
  16dcb8:	4d 85 ed             	test   %r13,%r13
  16dcbb:	0f 84 a0 01 00 00    	je     16de61 <native.support.doe_native_command_types.tryMergeDispatchIntoLast+0x1c1>
  16dcc1:	f6 86 90 30 00 00 0f 	testb  $0xf,0x3090(%rsi)
  16dcc8:	0f 85 93 01 00 00    	jne    16de61 <native.support.doe_native_command_types.tryMergeDispatchIntoLast+0x1c1>
  16dcce:	44 8b be 7c 30 00 00 	mov    0x307c(%rsi),%r15d
  16dcd5:	4c 8d b5 40 cf ff ff 	lea    -0x30c0(%rbp),%r14
  16dcdc:	ba 7c 30 00 00       	mov    $0x307c,%edx
  16dce1:	49 89 fc             	mov    %rdi,%r12
  16dce4:	48 89 f3             	mov    %rsi,%rbx
  16dce7:	4c 89 f7             	mov    %r14,%rdi
  16dcea:	e8 81 7d 0c 00       	call   235a70 <memcpy>
  16dcef:	44 89 7d bc          	mov    %r15d,-0x44(%rbp)
  16dcf3:	49 69 c5 a0 30 00 00 	imul   $0x30a0,%r13,%rax
  16dcfa:	c5 f9 6f 83 80 30 00 	vmovdqa 0x3080(%rbx),%xmm0
  16dd01:	00 
  16dd02:	c5 f9 7f 45 c0       	vmovdqa %xmm0,-0x40(%rbp)
  16dd07:	4d 8b 24 24          	mov    (%r12),%r12
  16dd0b:	41 80 7c 04 f0 00    	cmpb   $0x0,-0x10(%r12,%rax,1)
  16dd11:	0f 85 4a 01 00 00    	jne    16de61 <native.support.doe_native_command_types.tryMergeDispatchIntoLast+0x1c1>
  16dd17:	49 01 c4             	add    %rax,%r12
  16dd1a:	49 8b 84 24 90 f3 ff 	mov    -0xc70(%r12),%rax
  16dd21:	ff 
  16dd22:	48 3b 85 70 f3 ff ff 	cmp    -0xc90(%rbp),%rax
  16dd29:	0f 85 32 01 00 00    	jne    16de61 <native.support.doe_native_command_types.tryMergeDispatchIntoLast+0x1c1>
  16dd2f:	49 8b 84 24 98 f3 ff 	mov    -0xc68(%r12),%rax
  16dd36:	ff 
  16dd37:	48 3b 85 78 f3 ff ff 	cmp    -0xc88(%rbp),%rax
  16dd3e:	0f 85 1d 01 00 00    	jne    16de61 <native.support.doe_native_command_types.tryMergeDispatchIntoLast+0x1c1>
  16dd44:	41 0f b6 44 24 e0    	movzbl -0x20(%r12),%eax
  16dd4a:	3a 45 c0             	cmp    -0x40(%rbp),%al
  16dd4d:	0f 85 0e 01 00 00    	jne    16de61 <native.support.doe_native_command_types.tryMergeDispatchIntoLast+0x1c1>
  16dd53:	41 8b 5c 24 c0       	mov    -0x40(%r12),%ebx
  16dd58:	3b 5d a0             	cmp    -0x60(%rbp),%ebx
  16dd5b:	0f 85 00 01 00 00    	jne    16de61 <native.support.doe_native_command_types.tryMergeDispatchIntoLast+0x1c1>
  16dd61:	41 8b 44 24 c4       	mov    -0x3c(%r12),%eax
  16dd66:	3b 45 a4             	cmp    -0x5c(%rbp),%eax
  16dd69:	0f 85 f2 00 00 00    	jne    16de61 <native.support.doe_native_command_types.tryMergeDispatchIntoLast+0x1c1>
  16dd6f:	41 8b 44 24 c8       	mov    -0x38(%r12),%eax
  16dd74:	3b 45 a8             	cmp    -0x58(%rbp),%eax
  16dd77:	0f 85 e4 00 00 00    	jne    16de61 <native.support.doe_native_command_types.tryMergeDispatchIntoLast+0x1c1>
  16dd7d:	41 8b 44 24 cc       	mov    -0x34(%r12),%eax
  16dd82:	3b 45 ac             	cmp    -0x54(%rbp),%eax
  16dd85:	0f 85 d6 00 00 00    	jne    16de61 <native.support.doe_native_command_types.tryMergeDispatchIntoLast+0x1c1>
  16dd8b:	41 8b 44 24 d0       	mov    -0x30(%r12),%eax
  16dd90:	3b 45 b0             	cmp    -0x50(%rbp),%eax
  16dd93:	0f 85 c8 00 00 00    	jne    16de61 <native.support.doe_native_command_types.tryMergeDispatchIntoLast+0x1c1>
  16dd99:	41 8b 44 24 d4       	mov    -0x2c(%r12),%eax
  16dd9e:	3b 45 b4             	cmp    -0x4c(%rbp),%eax
  16dda1:	0f 85 ba 00 00 00    	jne    16de61 <native.support.doe_native_command_types.tryMergeDispatchIntoLast+0x1c1>
  16dda7:	41 8b 44 24 d8       	mov    -0x28(%r12),%eax
  16ddac:	3b 45 b8             	cmp    -0x48(%rbp),%eax
  16ddaf:	0f 85 ac 00 00 00    	jne    16de61 <native.support.doe_native_command_types.tryMergeDispatchIntoLast+0x1c1>
  16ddb5:	49 8d 84 24 60 cf ff 	lea    -0x30a0(%r12),%rax
  16ddbc:	ff 
  16ddbd:	4c 39 f0             	cmp    %r14,%rax
  16ddc0:	74 24                	je     16dde6 <native.support.doe_native_command_types.tryMergeDispatchIntoLast+0x146>
  16ddc2:	c4 c1 7a 6f 44 24 a0 	vmovdqu -0x60(%r12),%xmm0
  16ddc9:	c4 c1 7a 6f 4c 24 b0 	vmovdqu -0x50(%r12),%xmm1
  16ddd0:	62 f3 7d 08 3f 45 f8 	vpcmpneqb -0x80(%rbp),%xmm0,%k0
  16ddd7:	04 
  16ddd8:	62 f3 75 08 3f 4d f9 	vpcmpneqb -0x70(%rbp),%xmm1,%k1
  16dddf:	04 
  16dde0:	c5 f8 98 c1          	kortestw %k1,%k0
  16dde4:	75 7b                	jne    16de61 <native.support.doe_native_command_types.tryMergeDispatchIntoLast+0x1c1>
  16dde6:	49 8d bc 24 a0 f3 ff 	lea    -0xc60(%r12),%rdi
  16dded:	ff 
  16ddee:	48 8d 95 80 f3 ff ff 	lea    -0xc80(%rbp),%rdx
  16ddf5:	48 89 de             	mov    %rbx,%rsi
  16ddf8:	48 89 d9             	mov    %rbx,%rcx
  16ddfb:	e8 20 26 02 00       	call   190420 <mem.eql__anon_47794>
  16de00:	a8 01                	test   $0x1,%al
  16de02:	74 5d                	je     16de61 <native.support.doe_native_command_types.tryMergeDispatchIntoLast+0x1c1>
  16de04:	49 8d bc 24 a0 f7 ff 	lea    -0x860(%r12),%rdi
  16de0b:	ff 
  16de0c:	48 8d 95 80 f7 ff ff 	lea    -0x880(%rbp),%rdx
  16de13:	48 89 de             	mov    %rbx,%rsi
  16de16:	48 89 d9             	mov    %rbx,%rcx
  16de19:	e8 02 26 02 00       	call   190420 <mem.eql__anon_47794>
  16de1e:	a8 01                	test   $0x1,%al
  16de20:	74 3f                	je     16de61 <native.support.doe_native_command_types.tryMergeDispatchIntoLast+0x1c1>
  16de22:	49 8d bc 24 a0 fb ff 	lea    -0x460(%r12),%rdi
  16de29:	ff 
  16de2a:	48 8d 95 80 fb ff ff 	lea    -0x480(%rbp),%rdx
  16de31:	48 89 de             	mov    %rbx,%rsi
  16de34:	48 89 d9             	mov    %rbx,%rcx
  16de37:	e8 e4 25 02 00       	call   190420 <mem.eql__anon_47794>
  16de3c:	a8 01                	test   $0x1,%al
  16de3e:	74 21                	je     16de61 <native.support.doe_native_command_types.tryMergeDispatchIntoLast+0x1c1>
  16de40:	41 8b 44 24 dc       	mov    -0x24(%r12),%eax
  16de45:	83 f8 01             	cmp    $0x1,%eax
  16de48:	83 d0 00             	adc    $0x0,%eax
  16de4b:	41 83 ff 01          	cmp    $0x1,%r15d
  16de4f:	41 83 d7 00          	adc    $0x0,%r15d
  16de53:	41 01 c7             	add    %eax,%r15d
  16de56:	0f 92 c0             	setb   %al
  16de59:	0f 92 45 d4          	setb   -0x2c(%rbp)
  16de5d:	84 c0                	test   %al,%al
  16de5f:	74 14                	je     16de75 <native.support.doe_native_command_types.tryMergeDispatchIntoLast+0x1d5>
  16de61:	31 c0                	xor    %eax,%eax
  16de63:	48 81 c4 98 30 00 00 	add    $0x3098,%rsp
  16de6a:	5b                   	pop    %rbx
  16de6b:	41 5c                	pop    %r12
  16de6d:	41 5d                	pop    %r13
  16de6f:	41 5e                	pop    %r14
  16de71:	41 5f                	pop    %r15
  16de73:	5d                   	pop    %rbp
  16de74:	c3                   	ret
  16de75:	45 89 7c 24 dc       	mov    %r15d,-0x24(%r12)
  16de7a:	b0 01                	mov    $0x1,%al
  16de7c:	eb e5                	jmp    16de63 <native.support.doe_native_command_types.tryMergeDispatchIntoLast+0x1c3>

Disassembly of section .plt:
