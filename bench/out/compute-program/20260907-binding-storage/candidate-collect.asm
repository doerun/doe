
packages/doe-gpu-linux-x64/bin/libwebgpu_doe.so:     file format elf64-x86-64


Disassembly of section .init:

Disassembly of section .fini:

Disassembly of section .text:

000000000015f560 <native.vulkan.vulkan_compute_native.vulkan_collect_recorded_bind_group_state>:
  15f560:	55                   	push   %rbp
  15f561:	48 89 e5             	mov    %rsp,%rbp
  15f564:	53                   	push   %rbx
  15f565:	48 83 ec 28          	sub    $0x28,%rsp
  15f569:	48 89 d3             	mov    %rdx,%rbx
  15f56c:	48 89 f2             	mov    %rsi,%rdx
  15f56f:	48 89 fe             	mov    %rdi,%rsi
  15f572:	48 8d 4b 20          	lea    0x20(%rbx),%rcx
  15f576:	48 8d 7d d0          	lea    -0x30(%rbp),%rdi
  15f57a:	e8 21 bd f6 ff       	call   cb2a0 <native.vulkan.vulkan_compute_native.collectDispatchBindings>
  15f57f:	c5 f8 28 45 d0       	vmovaps -0x30(%rbp),%xmm0
  15f584:	c5 f8 29 03          	vmovaps %xmm0,(%rbx)
  15f588:	c5 f8 28 45 e0       	vmovaps -0x20(%rbp),%xmm0
  15f58d:	c5 f8 29 43 10       	vmovaps %xmm0,0x10(%rbx)
  15f592:	c6 83 20 24 00 00 01 	movb   $0x1,0x2420(%rbx)
  15f599:	48 83 c4 28          	add    $0x28,%rsp
  15f59d:	5b                   	pop    %rbx
  15f59e:	5d                   	pop    %rbp
  15f59f:	c3                   	ret

Disassembly of section .plt:
