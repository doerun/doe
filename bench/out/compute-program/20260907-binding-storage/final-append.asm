
packages/doe-gpu-linux-x64/bin/libwebgpu_doe.so:     file format elf64-x86-64


Disassembly of section .init:

Disassembly of section .fini:

Disassembly of section .text:

0000000000147470 <native.compute.doe_compute_ext_native.appendRecordedDispatch>:
  147470:	55                   	push   %rbp
  147471:	48 89 e5             	mov    %rsp,%rbp
  147474:	41 57                	push   %r15
  147476:	41 56                	push   %r14
  147478:	41 55                	push   %r13
  14747a:	41 54                	push   %r12
  14747c:	53                   	push   %rbx
  14747d:	48 81 ec 18 31 00 00 	sub    $0x3118,%rsp
  147484:	48 8b 07             	mov    (%rdi),%rax
  147487:	49 89 f6             	mov    %rsi,%r14
  14748a:	0f b6 70 18          	movzbl 0x18(%rax),%esi
  14748e:	83 fe 02             	cmp    $0x2,%esi
  147491:	0f 84 ef 02 00 00    	je     147786 <native.compute.doe_compute_ext_native.appendRecordedDispatch+0x316>
  147497:	83 fe 01             	cmp    $0x1,%esi
  14749a:	0f 85 69 02 00 00    	jne    147709 <native.compute.doe_compute_ext_native.appendRecordedDispatch+0x299>
  1474a0:	48 89 fb             	mov    %rdi,%rbx
  1474a3:	48 39 78 10          	cmp    %rdi,0x10(%rax)
  1474a7:	0f 85 5c 02 00 00    	jne    147709 <native.compute.doe_compute_ext_native.appendRecordedDispatch+0x299>
  1474ad:	48 8b 70 38          	mov    0x38(%rax),%rsi
  1474b1:	48 85 f6             	test   %rsi,%rsi
  1474b4:	74 63                	je     147519 <native.compute.doe_compute_ext_native.appendRecordedDispatch+0xa9>
  1474b6:	48 8b 7b 38          	mov    0x38(%rbx),%rdi
  1474ba:	48 3b 7b 30          	cmp    0x30(%rbx),%rdi
  1474be:	75 59                	jne    147519 <native.compute.doe_compute_ext_native.appendRecordedDispatch+0xa9>
  1474c0:	48 ff ce             	dec    %rsi
  1474c3:	48 39 73 40          	cmp    %rsi,0x40(%rbx)
  1474c7:	75 50                	jne    147519 <native.compute.doe_compute_ext_native.appendRecordedDispatch+0xa9>
  1474c9:	4c 39 73 48          	cmp    %r14,0x48(%rbx)
  1474cd:	75 4a                	jne    147519 <native.compute.doe_compute_ext_native.appendRecordedDispatch+0xa9>
  1474cf:	39 53 60             	cmp    %edx,0x60(%rbx)
  1474d2:	75 45                	jne    147519 <native.compute.doe_compute_ext_native.appendRecordedDispatch+0xa9>
  1474d4:	39 4b 64             	cmp    %ecx,0x64(%rbx)
  1474d7:	75 40                	jne    147519 <native.compute.doe_compute_ext_native.appendRecordedDispatch+0xa9>
  1474d9:	44 39 43 68          	cmp    %r8d,0x68(%rbx)
  1474dd:	75 3a                	jne    147519 <native.compute.doe_compute_ext_native.appendRecordedDispatch+0xa9>
  1474df:	48 8b 40 30          	mov    0x30(%rax),%rax
  1474e3:	48 69 f6 a0 30 00 00 	imul   $0x30a0,%rsi,%rsi
  1474ea:	80 bc 30 90 30 00 00 	cmpb   $0x0,0x3090(%rax,%rsi,1)
  1474f1:	00 
  1474f2:	75 25                	jne    147519 <native.compute.doe_compute_ext_native.appendRecordedDispatch+0xa9>
  1474f4:	48 01 f0             	add    %rsi,%rax
  1474f7:	8b b0 7c 30 00 00    	mov    0x307c(%rax),%esi
  1474fd:	83 fe 01             	cmp    $0x1,%esi
  147500:	83 d6 00             	adc    $0x0,%esi
  147503:	ff c6                	inc    %esi
  147505:	40 0f 94 c7          	sete   %dil
  147509:	0f 94 85 70 ff ff ff 	sete   -0x90(%rbp)
  147510:	40 84 ff             	test   %dil,%dil
  147513:	0f 84 86 02 00 00    	je     14779f <native.compute.doe_compute_ext_native.appendRecordedDispatch+0x32f>
  147519:	89 55 9c             	mov    %edx,-0x64(%rbp)
  14751c:	89 4d a0             	mov    %ecx,-0x60(%rbp)
  14751f:	44 89 45 a4          	mov    %r8d,-0x5c(%rbp)
  147523:	89 55 b4             	mov    %edx,-0x4c(%rbp)
  147526:	89 4d b8             	mov    %ecx,-0x48(%rbp)
  147529:	44 89 45 bc          	mov    %r8d,-0x44(%rbp)
  14752d:	4c 8d 7b 10          	lea    0x10(%rbx),%r15
  147531:	41 8b 86 80 88 04 00 	mov    0x48880(%r14),%eax
  147538:	45 8b 86 90 8a 04 00 	mov    0x48a90(%r14),%r8d
  14753f:	45 8b 8e 8c 88 04 00 	mov    0x4888c(%r14),%r9d
  147546:	49 8b be 50 87 04 00 	mov    0x48750(%r14),%rdi
  14754d:	49 8b b6 58 87 04 00 	mov    0x48758(%r14),%rsi
  147554:	49 8b 96 60 87 04 00 	mov    0x48760(%r14),%rdx
  14755b:	49 8b 8e 68 87 04 00 	mov    0x48768(%r14),%rcx
  147562:	89 85 70 ff ff ff    	mov    %eax,-0x90(%rbp)
  147568:	44 89 85 74 ff ff ff 	mov    %r8d,-0x8c(%rbp)
  14756f:	44 89 8d 78 ff ff ff 	mov    %r9d,-0x88(%rbp)
  147576:	48 8d 85 70 ff ff ff 	lea    -0x90(%rbp),%rax
  14757d:	4c 8d 4d 9c          	lea    -0x64(%rbp),%r9
  147581:	4d 89 f8             	mov    %r15,%r8
  147584:	48 89 04 24          	mov    %rax,(%rsp)
  147588:	e8 73 7e fb ff       	call   ff400 <native.compute.doe_compute_preconditions_native.validate_bind_groups>
  14758d:	66 85 c0             	test   %ax,%ax
  147590:	0f 85 02 02 00 00    	jne    147798 <native.compute.doe_compute_ext_native.appendRecordedDispatch+0x328>
  147596:	41 8b 86 80 88 04 00 	mov    0x48880(%r14),%eax
  14759d:	41 8b 96 90 8a 04 00 	mov    0x48a90(%r14),%edx
  1475a4:	45 0f b6 ae 23 8b 04 	movzbl 0x48b23(%r14),%r13d
  1475ab:	00 
  1475ac:	41 8b 8e 8c 88 04 00 	mov    0x4888c(%r14),%ecx
  1475b3:	4d 8b a6 18 02 00 00 	mov    0x218(%r14),%r12
  1475ba:	48 8d bd d0 ce ff ff 	lea    -0x3130(%rbp),%rdi
  1475c1:	c6 45 d0 00          	movb   $0x0,-0x30(%rbp)
  1475c5:	31 f6                	xor    %esi,%esi
  1475c7:	89 45 a8             	mov    %eax,-0x58(%rbp)
  1475ca:	89 55 ac             	mov    %edx,-0x54(%rbp)
  1475cd:	ba 30 24 00 00       	mov    $0x2430,%edx
  1475d2:	89 4d b0             	mov    %ecx,-0x50(%rbp)
  1475d5:	44 88 6d c0          	mov    %r13b,-0x40(%rbp)
  1475d9:	e8 52 e6 0e 00       	call   235c30 <memset>
  1475de:	4c 89 b5 00 f3 ff ff 	mov    %r14,-0xd00(%rbp)
  1475e5:	4c 89 a5 08 f3 ff ff 	mov    %r12,-0xcf8(%rbp)
  1475ec:	4c 8d a5 10 f3 ff ff 	lea    -0xcf0(%rbp),%r12
  1475f3:	ba 00 0c 00 00       	mov    $0xc00,%edx
  1475f8:	31 f6                	xor    %esi,%esi
  1475fa:	4c 89 e7             	mov    %r12,%rdi
  1475fd:	e8 2e e6 0e 00       	call   235c30 <memset>
  147602:	8b 45 b4             	mov    -0x4c(%rbp),%eax
  147605:	48 8d 95 10 f7 ff ff 	lea    -0x8f0(%rbp),%rdx
  14760c:	48 8d 8d 10 fb ff ff 	lea    -0x4f0(%rbp),%rcx
  147613:	4c 89 ff             	mov    %r15,%rdi
  147616:	4c 89 e6             	mov    %r12,%rsi
  147619:	89 85 34 ff ff ff    	mov    %eax,-0xcc(%rbp)
  14761f:	8b 45 b8             	mov    -0x48(%rbp),%eax
  147622:	89 85 38 ff ff ff    	mov    %eax,-0xc8(%rbp)
  147628:	8b 45 bc             	mov    -0x44(%rbp),%eax
  14762b:	89 85 3c ff ff ff    	mov    %eax,-0xc4(%rbp)
  147631:	8b 45 a8             	mov    -0x58(%rbp),%eax
  147634:	89 85 40 ff ff ff    	mov    %eax,-0xc0(%rbp)
  14763a:	8b 45 ac             	mov    -0x54(%rbp),%eax
  14763d:	89 85 44 ff ff ff    	mov    %eax,-0xbc(%rbp)
  147643:	8b 45 b0             	mov    -0x50(%rbp),%eax
  147646:	89 85 48 ff ff ff    	mov    %eax,-0xb8(%rbp)
  14764c:	0f b6 45 d0          	movzbl -0x30(%rbp),%eax
  147650:	c7 85 4c ff ff ff 01 	movl   $0x1,-0xb4(%rbp)
  147657:	00 00 00 
  14765a:	44 88 ad 50 ff ff ff 	mov    %r13b,-0xb0(%rbp)
  147661:	88 85 60 ff ff ff    	mov    %al,-0xa0(%rbp)
  147667:	c4 c1 7c 10 07       	vmovups (%r15),%ymm0
  14766c:	c5 fc 11 85 10 ff ff 	vmovups %ymm0,-0xf0(%rbp)
  147673:	ff 
  147674:	c5 f8 77             	vzeroupper
  147677:	e8 54 90 fb ff       	call   1006d0 <native.compute.doe_compute_bind_groups.populateFlatBindings>
  14767c:	89 85 30 ff ff ff    	mov    %eax,-0xd0(%rbp)
  147682:	49 83 be 30 03 00 00 	cmpq   $0x0,0x330(%r14)
  147689:	00 
  14768a:	74 3d                	je     1476c9 <native.compute.doe_compute_ext_native.appendRecordedDispatch+0x259>
  14768c:	48 8d 8d f0 ce ff ff 	lea    -0x3110(%rbp),%rcx
  147693:	48 8d bd 70 ff ff ff 	lea    -0x90(%rbp),%rdi
  14769a:	4c 89 f6             	mov    %r14,%rsi
  14769d:	4c 89 fa             	mov    %r15,%rdx
  1476a0:	e8 fb 3b f8 ff       	call   cb2a0 <native.vulkan.vulkan_compute_native.collectDispatchBindings>
  1476a5:	c5 f8 28 85 70 ff ff 	vmovaps -0x90(%rbp),%xmm0
  1476ac:	ff 
  1476ad:	c5 f8 28 4d 80       	vmovaps -0x80(%rbp),%xmm1
  1476b2:	c5 f8 29 85 d0 ce ff 	vmovaps %xmm0,-0x3130(%rbp)
  1476b9:	ff 
  1476ba:	c5 f8 29 8d e0 ce ff 	vmovaps %xmm1,-0x3120(%rbp)
  1476c1:	ff 
  1476c2:	c6 85 f0 f2 ff ff 01 	movb   $0x1,-0xd10(%rbp)
  1476c9:	48 8b 03             	mov    (%rbx),%rax
  1476cc:	48 8d 95 d0 ce ff ff 	lea    -0x3130(%rbp),%rdx
  1476d3:	48 8b 78 30          	mov    0x30(%rax),%rdi
  1476d7:	48 8b 70 38          	mov    0x38(%rax),%rsi
  1476db:	e8 c0 65 02 00       	call   16dca0 <native.support.doe_native_command_types.tryMergeDispatchIntoLast>
  1476e0:	48 8b 3b             	mov    (%rbx),%rdi
  1476e3:	a8 01                	test   $0x1,%al
  1476e5:	74 5c                	je     147743 <native.compute.doe_compute_ext_native.appendRecordedDispatch+0x2d3>
  1476e7:	48 83 7f 38 00       	cmpq   $0x0,0x38(%rdi)
  1476ec:	8b 45 bc             	mov    -0x44(%rbp),%eax
  1476ef:	8b 4d b8             	mov    -0x48(%rbp),%ecx
  1476f2:	8b 55 b4             	mov    -0x4c(%rbp),%edx
  1476f5:	0f 84 8b 00 00 00    	je     147786 <native.compute.doe_compute_ext_native.appendRecordedDispatch+0x316>
  1476fb:	48 8b 73 30          	mov    0x30(%rbx),%rsi
  1476ff:	48 89 73 38          	mov    %rsi,0x38(%rbx)
  147703:	48 8b 77 38          	mov    0x38(%rdi),%rsi
  147707:	eb 69                	jmp    147772 <native.compute.doe_compute_ext_native.appendRecordedDispatch+0x302>
  147709:	c6 40 18 02          	movb   $0x2,0x18(%rax)
  14770d:	66 c7 40 10 12 00    	movw   $0x12,0x10(%rax)
  147713:	bf 50 1a 00 00       	mov    $0x1a50,%edi
  147718:	48 8d 15 22 0a f6 ff 	lea    -0x9f5de(%rip),%rdx        # a8141 <__anon_43098>
  14771f:	b9 41 00 00 00       	mov    $0x41,%ecx
  147724:	be 02 00 00 00       	mov    $0x2,%esi
  147729:	48 03 78 20          	add    0x20(%rax),%rdi
  14772d:	48 81 c4 18 31 00 00 	add    $0x3118,%rsp
  147734:	5b                   	pop    %rbx
  147735:	41 5c                	pop    %r12
  147737:	41 5d                	pop    %r13
  147739:	41 5e                	pop    %r14
  14773b:	41 5f                	pop    %r15
  14773d:	5d                   	pop    %rbp
  14773e:	e9 ed fe fb ff       	jmp    107630 <runtime.diagnostics.error_scope.ErrorScopeStack.deliver>
  147743:	48 8d b5 d0 ce ff ff 	lea    -0x3130(%rbp),%rsi
  14774a:	e8 11 18 00 00       	call   148f60 <native.command.doe_command_recording.append>
  14774f:	8b 4d b8             	mov    -0x48(%rbp),%ecx
  147752:	8b 55 b4             	mov    -0x4c(%rbp),%edx
  147755:	a8 01                	test   $0x1,%al
  147757:	8b 45 bc             	mov    -0x44(%rbp),%eax
  14775a:	74 2a                	je     147786 <native.compute.doe_compute_ext_native.appendRecordedDispatch+0x316>
  14775c:	48 8b 33             	mov    (%rbx),%rsi
  14775f:	48 83 7e 38 00       	cmpq   $0x0,0x38(%rsi)
  147764:	74 20                	je     147786 <native.compute.doe_compute_ext_native.appendRecordedDispatch+0x316>
  147766:	48 8b 7b 30          	mov    0x30(%rbx),%rdi
  14776a:	48 89 7b 38          	mov    %rdi,0x38(%rbx)
  14776e:	48 8b 76 38          	mov    0x38(%rsi),%rsi
  147772:	48 ff ce             	dec    %rsi
  147775:	48 89 73 40          	mov    %rsi,0x40(%rbx)
  147779:	4c 89 73 48          	mov    %r14,0x48(%rbx)
  14777d:	89 53 60             	mov    %edx,0x60(%rbx)
  147780:	89 4b 64             	mov    %ecx,0x64(%rbx)
  147783:	89 43 68             	mov    %eax,0x68(%rbx)
  147786:	48 81 c4 18 31 00 00 	add    $0x3118,%rsp
  14778d:	5b                   	pop    %rbx
  14778e:	41 5c                	pop    %r12
  147790:	41 5d                	pop    %r13
  147792:	41 5e                	pop    %r14
  147794:	41 5f                	pop    %r15
  147796:	5d                   	pop    %rbp
  147797:	c3                   	ret
  147798:	e8 43 08 0e 00       	call   227fe0 <log.scoped(.default).err__anon_40062>
  14779d:	eb e7                	jmp    147786 <native.compute.doe_compute_ext_native.appendRecordedDispatch+0x316>
  14779f:	89 b0 7c 30 00 00    	mov    %esi,0x307c(%rax)
  1477a5:	eb df                	jmp    147786 <native.compute.doe_compute_ext_native.appendRecordedDispatch+0x316>

Disassembly of section .plt:
