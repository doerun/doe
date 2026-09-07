
packages/doe-gpu-linux-x64/bin/libwebgpu_doe.so:     file format elf64-x86-64


Disassembly of section .init:

Disassembly of section .fini:

Disassembly of section .text:

00000000001498e0 <native.compute.doe_compute_ext_native.appendRecordedDispatch>:
  1498e0:	55                   	push   %rbp
  1498e1:	48 89 e5             	mov    %rsp,%rbp
  1498e4:	41 57                	push   %r15
  1498e6:	41 56                	push   %r14
  1498e8:	41 55                	push   %r13
  1498ea:	41 54                	push   %r12
  1498ec:	53                   	push   %rbx
  1498ed:	48 81 ec 38 9d 00 00 	sub    $0x9d38,%rsp
  1498f4:	48 8b 07             	mov    (%rdi),%rax
  1498f7:	49 89 f6             	mov    %rsi,%r14
  1498fa:	0f b6 70 18          	movzbl 0x18(%rax),%esi
  1498fe:	83 fe 02             	cmp    $0x2,%esi
  149901:	0f 84 63 03 00 00    	je     149c6a <native.compute.doe_compute_ext_native.appendRecordedDispatch+0x38a>
  149907:	83 fe 01             	cmp    $0x1,%esi
  14990a:	0f 85 dd 02 00 00    	jne    149bed <native.compute.doe_compute_ext_native.appendRecordedDispatch+0x30d>
  149910:	48 89 fb             	mov    %rdi,%rbx
  149913:	48 39 78 10          	cmp    %rdi,0x10(%rax)
  149917:	0f 85 d0 02 00 00    	jne    149bed <native.compute.doe_compute_ext_native.appendRecordedDispatch+0x30d>
  14991d:	48 8b 70 38          	mov    0x38(%rax),%rsi
  149921:	48 85 f6             	test   %rsi,%rsi
  149924:	74 63                	je     149989 <native.compute.doe_compute_ext_native.appendRecordedDispatch+0xa9>
  149926:	48 8b 7b 38          	mov    0x38(%rbx),%rdi
  14992a:	48 3b 7b 30          	cmp    0x30(%rbx),%rdi
  14992e:	75 59                	jne    149989 <native.compute.doe_compute_ext_native.appendRecordedDispatch+0xa9>
  149930:	48 ff ce             	dec    %rsi
  149933:	48 39 73 40          	cmp    %rsi,0x40(%rbx)
  149937:	75 50                	jne    149989 <native.compute.doe_compute_ext_native.appendRecordedDispatch+0xa9>
  149939:	4c 39 73 48          	cmp    %r14,0x48(%rbx)
  14993d:	75 4a                	jne    149989 <native.compute.doe_compute_ext_native.appendRecordedDispatch+0xa9>
  14993f:	39 53 60             	cmp    %edx,0x60(%rbx)
  149942:	75 45                	jne    149989 <native.compute.doe_compute_ext_native.appendRecordedDispatch+0xa9>
  149944:	39 4b 64             	cmp    %ecx,0x64(%rbx)
  149947:	75 40                	jne    149989 <native.compute.doe_compute_ext_native.appendRecordedDispatch+0xa9>
  149949:	44 39 43 68          	cmp    %r8d,0x68(%rbx)
  14994d:	75 3a                	jne    149989 <native.compute.doe_compute_ext_native.appendRecordedDispatch+0xa9>
  14994f:	48 8b 40 30          	mov    0x30(%rax),%rax
  149953:	48 69 f6 a0 30 00 00 	imul   $0x30a0,%rsi,%rsi
  14995a:	80 bc 30 90 30 00 00 	cmpb   $0x0,0x3090(%rax,%rsi,1)
  149961:	00 
  149962:	75 25                	jne    149989 <native.compute.doe_compute_ext_native.appendRecordedDispatch+0xa9>
  149964:	48 01 f0             	add    %rsi,%rax
  149967:	8b b0 7c 30 00 00    	mov    0x307c(%rax),%esi
  14996d:	83 fe 01             	cmp    $0x1,%esi
  149970:	83 d6 00             	adc    $0x0,%esi
  149973:	ff c6                	inc    %esi
  149975:	40 0f 94 c7          	sete   %dil
  149979:	0f 94 85 c0 aa ff ff 	sete   -0x5540(%rbp)
  149980:	40 84 ff             	test   %dil,%dil
  149983:	0f 84 fa 02 00 00    	je     149c83 <native.compute.doe_compute_ext_native.appendRecordedDispatch+0x3a3>
  149989:	89 55 a4             	mov    %edx,-0x5c(%rbp)
  14998c:	89 4d a8             	mov    %ecx,-0x58(%rbp)
  14998f:	44 89 45 ac          	mov    %r8d,-0x54(%rbp)
  149993:	89 55 b4             	mov    %edx,-0x4c(%rbp)
  149996:	89 4d b8             	mov    %ecx,-0x48(%rbp)
  149999:	44 89 45 bc          	mov    %r8d,-0x44(%rbp)
  14999d:	4c 8d 7b 10          	lea    0x10(%rbx),%r15
  1499a1:	41 8b 86 80 88 04 00 	mov    0x48880(%r14),%eax
  1499a8:	45 8b 86 90 8a 04 00 	mov    0x48a90(%r14),%r8d
  1499af:	45 8b 8e 8c 88 04 00 	mov    0x4888c(%r14),%r9d
  1499b6:	49 8b be 50 87 04 00 	mov    0x48750(%r14),%rdi
  1499bd:	49 8b b6 58 87 04 00 	mov    0x48758(%r14),%rsi
  1499c4:	49 8b 96 60 87 04 00 	mov    0x48760(%r14),%rdx
  1499cb:	49 8b 8e 68 87 04 00 	mov    0x48768(%r14),%rcx
  1499d2:	89 85 c0 aa ff ff    	mov    %eax,-0x5540(%rbp)
  1499d8:	44 89 85 c4 aa ff ff 	mov    %r8d,-0x553c(%rbp)
  1499df:	44 89 8d c8 aa ff ff 	mov    %r9d,-0x5538(%rbp)
  1499e6:	48 8d 85 c0 aa ff ff 	lea    -0x5540(%rbp),%rax
  1499ed:	4c 8d 4d a4          	lea    -0x5c(%rbp),%r9
  1499f1:	4d 89 f8             	mov    %r15,%r8
  1499f4:	48 89 04 24          	mov    %rax,(%rsp)
  1499f8:	e8 73 7e fb ff       	call   101870 <native.compute.doe_compute_preconditions_native.validate_bind_groups>
  1499fd:	66 85 c0             	test   %ax,%ax
  149a00:	0f 85 76 02 00 00    	jne    149c7c <native.compute.doe_compute_ext_native.appendRecordedDispatch+0x39c>
  149a06:	41 8b 86 80 88 04 00 	mov    0x48880(%r14),%eax
  149a0d:	41 8b 96 90 8a 04 00 	mov    0x48a90(%r14),%edx
  149a14:	45 0f b6 ae 23 8b 04 	movzbl 0x48b23(%r14),%r13d
  149a1b:	00 
  149a1c:	41 8b 8e 8c 88 04 00 	mov    0x4888c(%r14),%ecx
  149a23:	4d 8b a6 18 02 00 00 	mov    0x218(%r14),%r12
  149a2a:	48 8d bd e0 ce ff ff 	lea    -0x3120(%rbp),%rdi
  149a31:	c6 45 d0 00          	movb   $0x0,-0x30(%rbp)
  149a35:	31 f6                	xor    %esi,%esi
  149a37:	89 45 80             	mov    %eax,-0x80(%rbp)
  149a3a:	89 55 90             	mov    %edx,-0x70(%rbp)
  149a3d:	ba 30 24 00 00       	mov    $0x2430,%edx
  149a42:	89 4d b0             	mov    %ecx,-0x50(%rbp)
  149a45:	44 88 6d c0          	mov    %r13b,-0x40(%rbp)
  149a49:	e8 52 e8 0e 00       	call   2382a0 <memset>
  149a4e:	4c 89 b5 10 f3 ff ff 	mov    %r14,-0xcf0(%rbp)
  149a55:	4c 89 a5 18 f3 ff ff 	mov    %r12,-0xce8(%rbp)
  149a5c:	4c 8d a5 20 f3 ff ff 	lea    -0xce0(%rbp),%r12
  149a63:	ba 00 0c 00 00       	mov    $0xc00,%edx
  149a68:	31 f6                	xor    %esi,%esi
  149a6a:	4c 89 e7             	mov    %r12,%rdi
  149a6d:	e8 2e e8 0e 00       	call   2382a0 <memset>
  149a72:	8b 45 b4             	mov    -0x4c(%rbp),%eax
  149a75:	48 8d 95 20 f7 ff ff 	lea    -0x8e0(%rbp),%rdx
  149a7c:	48 8d 8d 20 fb ff ff 	lea    -0x4e0(%rbp),%rcx
  149a83:	4c 89 ff             	mov    %r15,%rdi
  149a86:	4c 89 e6             	mov    %r12,%rsi
  149a89:	89 85 44 ff ff ff    	mov    %eax,-0xbc(%rbp)
  149a8f:	8b 45 b8             	mov    -0x48(%rbp),%eax
  149a92:	89 85 48 ff ff ff    	mov    %eax,-0xb8(%rbp)
  149a98:	8b 45 bc             	mov    -0x44(%rbp),%eax
  149a9b:	89 85 4c ff ff ff    	mov    %eax,-0xb4(%rbp)
  149aa1:	8b 45 80             	mov    -0x80(%rbp),%eax
  149aa4:	89 85 50 ff ff ff    	mov    %eax,-0xb0(%rbp)
  149aaa:	8b 45 90             	mov    -0x70(%rbp),%eax
  149aad:	89 85 54 ff ff ff    	mov    %eax,-0xac(%rbp)
  149ab3:	8b 45 b0             	mov    -0x50(%rbp),%eax
  149ab6:	89 85 58 ff ff ff    	mov    %eax,-0xa8(%rbp)
  149abc:	0f b6 45 d0          	movzbl -0x30(%rbp),%eax
  149ac0:	c7 85 5c ff ff ff 01 	movl   $0x1,-0xa4(%rbp)
  149ac7:	00 00 00 
  149aca:	44 88 ad 60 ff ff ff 	mov    %r13b,-0xa0(%rbp)
  149ad1:	88 85 70 ff ff ff    	mov    %al,-0x90(%rbp)
  149ad7:	c4 c1 7c 10 07       	vmovups (%r15),%ymm0
  149adc:	c5 fc 11 85 20 ff ff 	vmovups %ymm0,-0xe0(%rbp)
  149ae3:	ff 
  149ae4:	c5 f8 77             	vzeroupper
  149ae7:	e8 54 90 fb ff       	call   102b40 <native.compute.doe_compute_bind_groups.populateFlatBindings>
  149aec:	89 85 40 ff ff ff    	mov    %eax,-0xc0(%rbp)
  149af2:	49 83 be 30 03 00 00 	cmpq   $0x0,0x330(%r14)
  149af9:	00 
  149afa:	0f 84 b1 00 00 00    	je     149bb1 <native.compute.doe_compute_ext_native.appendRecordedDispatch+0x2d1>
  149b00:	48 8d bd c0 aa ff ff 	lea    -0x5540(%rbp),%rdi
  149b07:	4c 89 f6             	mov    %r14,%rsi
  149b0a:	4c 89 fa             	mov    %r15,%rdx
  149b0d:	e8 6e 38 f8 ff       	call   cd380 <native.vulkan.vulkan_compute_native.vulkan_collect_dispatch_binding_state>
  149b12:	4c 8d a5 b0 62 ff ff 	lea    -0x9d50(%rbp),%r12
  149b19:	48 8d b5 e0 aa ff ff 	lea    -0x5520(%rbp),%rsi
  149b20:	ba 00 24 00 00       	mov    $0x2400,%edx
  149b25:	4c 89 e7             	mov    %r12,%rdi
  149b28:	e8 63 e5 0e 00       	call   238090 <memcpy>
  149b2d:	4c 8d bd b0 86 ff ff 	lea    -0x7950(%rbp),%r15
  149b34:	48 8d 35 05 65 ee ff 	lea    -0x119afb(%rip),%rsi        # 30040 <__anon_32967+0xea0>
  149b3b:	ba 10 24 00 00       	mov    $0x2410,%edx
  149b40:	4c 89 ff             	mov    %r15,%rdi
  149b43:	e8 48 e5 0e 00       	call   238090 <memcpy>
  149b48:	48 8b 85 d0 aa ff ff 	mov    -0x5530(%rbp),%rax
  149b4f:	c5 f8 28 85 c0 aa ff 	vmovaps -0x5540(%rbp),%xmm0
  149b56:	ff 
  149b57:	c5 f8 28 8d d0 aa ff 	vmovaps -0x5530(%rbp),%xmm1
  149b5e:	ff 
  149b5f:	c6 85 b0 aa ff ff 01 	movb   $0x1,-0x5550(%rbp)
  149b66:	4c 89 ff             	mov    %r15,%rdi
  149b69:	4c 89 e6             	mov    %r12,%rsi
  149b6c:	48 c1 e0 03          	shl    $0x3,%rax
  149b70:	48 8d 14 c0          	lea    (%rax,%rax,8),%rdx
  149b74:	c5 f8 29 45 80       	vmovaps %xmm0,-0x80(%rbp)
  149b79:	c5 f8 29 4d 90       	vmovaps %xmm1,-0x70(%rbp)
  149b7e:	e8 0d e5 0e 00       	call   238090 <memcpy>
  149b83:	c5 f8 28 45 80       	vmovaps -0x80(%rbp),%xmm0
  149b88:	c5 f8 28 4d 90       	vmovaps -0x70(%rbp),%xmm1
  149b8d:	48 8d bd 00 cf ff ff 	lea    -0x3100(%rbp),%rdi
  149b94:	ba 10 24 00 00       	mov    $0x2410,%edx
  149b99:	4c 89 fe             	mov    %r15,%rsi
  149b9c:	c5 f8 29 85 e0 ce ff 	vmovaps %xmm0,-0x3120(%rbp)
  149ba3:	ff 
  149ba4:	c5 f8 29 8d f0 ce ff 	vmovaps %xmm1,-0x3110(%rbp)
  149bab:	ff 
  149bac:	e8 df e4 0e 00       	call   238090 <memcpy>
  149bb1:	48 8b 3b             	mov    (%rbx),%rdi
  149bb4:	48 8d b5 e0 ce ff ff 	lea    -0x3120(%rbp),%rsi
  149bbb:	48 83 c7 30          	add    $0x30,%rdi
  149bbf:	e8 4c 66 02 00       	call   170210 <native.support.doe_native_command_types.tryMergeDispatchIntoLast>
  149bc4:	48 8b 3b             	mov    (%rbx),%rdi
  149bc7:	a8 01                	test   $0x1,%al
  149bc9:	74 5c                	je     149c27 <native.compute.doe_compute_ext_native.appendRecordedDispatch+0x347>
  149bcb:	48 83 7f 38 00       	cmpq   $0x0,0x38(%rdi)
  149bd0:	8b 45 bc             	mov    -0x44(%rbp),%eax
  149bd3:	8b 4d b8             	mov    -0x48(%rbp),%ecx
  149bd6:	8b 55 b4             	mov    -0x4c(%rbp),%edx
  149bd9:	0f 84 8b 00 00 00    	je     149c6a <native.compute.doe_compute_ext_native.appendRecordedDispatch+0x38a>
  149bdf:	48 8b 73 30          	mov    0x30(%rbx),%rsi
  149be3:	48 89 73 38          	mov    %rsi,0x38(%rbx)
  149be7:	48 8b 77 38          	mov    0x38(%rdi),%rsi
  149beb:	eb 69                	jmp    149c56 <native.compute.doe_compute_ext_native.appendRecordedDispatch+0x376>
  149bed:	c6 40 18 02          	movb   $0x2,0x18(%rax)
  149bf1:	66 c7 40 10 12 00    	movw   $0x12,0x10(%rax)
  149bf7:	bf 50 1a 00 00       	mov    $0x1a50,%edi
  149bfc:	48 8d 15 56 09 f6 ff 	lea    -0x9f6aa(%rip),%rdx        # aa559 <__anon_43085>
  149c03:	b9 41 00 00 00       	mov    $0x41,%ecx
  149c08:	be 02 00 00 00       	mov    $0x2,%esi
  149c0d:	48 03 78 20          	add    0x20(%rax),%rdi
  149c11:	48 81 c4 38 9d 00 00 	add    $0x9d38,%rsp
  149c18:	5b                   	pop    %rbx
  149c19:	41 5c                	pop    %r12
  149c1b:	41 5d                	pop    %r13
  149c1d:	41 5e                	pop    %r14
  149c1f:	41 5f                	pop    %r15
  149c21:	5d                   	pop    %rbp
  149c22:	e9 79 fe fb ff       	jmp    109aa0 <runtime.diagnostics.error_scope.ErrorScopeStack.deliver>
  149c27:	48 8d b5 e0 ce ff ff 	lea    -0x3120(%rbp),%rsi
  149c2e:	e8 0d 18 00 00       	call   14b440 <native.command.doe_command_recording.append>
  149c33:	8b 4d b8             	mov    -0x48(%rbp),%ecx
  149c36:	8b 55 b4             	mov    -0x4c(%rbp),%edx
  149c39:	a8 01                	test   $0x1,%al
  149c3b:	8b 45 bc             	mov    -0x44(%rbp),%eax
  149c3e:	74 2a                	je     149c6a <native.compute.doe_compute_ext_native.appendRecordedDispatch+0x38a>
  149c40:	48 8b 33             	mov    (%rbx),%rsi
  149c43:	48 83 7e 38 00       	cmpq   $0x0,0x38(%rsi)
  149c48:	74 20                	je     149c6a <native.compute.doe_compute_ext_native.appendRecordedDispatch+0x38a>
  149c4a:	48 8b 7b 30          	mov    0x30(%rbx),%rdi
  149c4e:	48 89 7b 38          	mov    %rdi,0x38(%rbx)
  149c52:	48 8b 76 38          	mov    0x38(%rsi),%rsi
  149c56:	48 ff ce             	dec    %rsi
  149c59:	48 89 73 40          	mov    %rsi,0x40(%rbx)
  149c5d:	4c 89 73 48          	mov    %r14,0x48(%rbx)
  149c61:	89 53 60             	mov    %edx,0x60(%rbx)
  149c64:	89 4b 64             	mov    %ecx,0x64(%rbx)
  149c67:	89 43 68             	mov    %eax,0x68(%rbx)
  149c6a:	48 81 c4 38 9d 00 00 	add    $0x9d38,%rsp
  149c71:	5b                   	pop    %rbx
  149c72:	41 5c                	pop    %r12
  149c74:	41 5d                	pop    %r13
  149c76:	41 5e                	pop    %r14
  149c78:	41 5f                	pop    %r15
  149c7a:	5d                   	pop    %rbp
  149c7b:	c3                   	ret
  149c7c:	e8 cf 09 0e 00       	call   22a650 <log.scoped(.default).err__anon_40051>
  149c81:	eb e7                	jmp    149c6a <native.compute.doe_compute_ext_native.appendRecordedDispatch+0x38a>
  149c83:	89 b0 7c 30 00 00    	mov    %esi,0x307c(%rax)
  149c89:	eb df                	jmp    149c6a <native.compute.doe_compute_ext_native.appendRecordedDispatch+0x38a>

Disassembly of section .plt:
