
packages/doe-gpu-linux-x64/bin/libwebgpu_doe.so:     file format elf64-x86-64


Disassembly of section .init:

Disassembly of section .fini:

Disassembly of section .text:

0000000000161a40 <native.vulkan.vulkan_compute_native.vulkan_collect_recorded_bind_group_state>:
  161a40:	55                   	push   %rbp
  161a41:	48 89 e5             	mov    %rsp,%rbp
  161a44:	41 57                	push   %r15
  161a46:	41 56                	push   %r14
  161a48:	53                   	push   %rbx
  161a49:	48 81 ec 58 6c 00 00 	sub    $0x6c58,%rsp
  161a50:	48 89 fb             	mov    %rdi,%rbx
  161a53:	48 8d bd a0 db ff ff 	lea    -0x2460(%rbp),%rdi
  161a5a:	e8 21 b9 f6 ff       	call   cd380 <native.vulkan.vulkan_compute_native.vulkan_collect_dispatch_binding_state>
  161a5f:	4c 8d bd 90 93 ff ff 	lea    -0x6c70(%rbp),%r15
  161a66:	48 8d b5 c0 db ff ff 	lea    -0x2440(%rbp),%rsi
  161a6d:	ba 00 24 00 00       	mov    $0x2400,%edx
  161a72:	4c 89 ff             	mov    %r15,%rdi
  161a75:	e8 16 66 0d 00       	call   238090 <memcpy>
  161a7a:	4c 8d b5 90 b7 ff ff 	lea    -0x4870(%rbp),%r14
  161a81:	48 8d 35 b8 e5 ec ff 	lea    -0x131a48(%rip),%rsi        # 30040 <__anon_32967+0xea0>
  161a88:	ba 10 24 00 00       	mov    $0x2410,%edx
  161a8d:	4c 89 f7             	mov    %r14,%rdi
  161a90:	e8 fb 65 0d 00       	call   238090 <memcpy>
  161a95:	48 8b 85 b0 db ff ff 	mov    -0x2450(%rbp),%rax
  161a9c:	c5 f8 28 85 a0 db ff 	vmovaps -0x2460(%rbp),%xmm0
  161aa3:	ff 
  161aa4:	c5 f8 28 8d b0 db ff 	vmovaps -0x2450(%rbp),%xmm1
  161aab:	ff 
  161aac:	c6 85 90 db ff ff 01 	movb   $0x1,-0x2470(%rbp)
  161ab3:	4c 89 f7             	mov    %r14,%rdi
  161ab6:	4c 89 fe             	mov    %r15,%rsi
  161ab9:	48 c1 e0 03          	shl    $0x3,%rax
  161abd:	48 8d 14 c0          	lea    (%rax,%rax,8),%rdx
  161ac1:	c5 f8 29 45 c0       	vmovaps %xmm0,-0x40(%rbp)
  161ac6:	c5 f8 29 4d d0       	vmovaps %xmm1,-0x30(%rbp)
  161acb:	e8 c0 65 0d 00       	call   238090 <memcpy>
  161ad0:	c5 f8 28 45 c0       	vmovaps -0x40(%rbp),%xmm0
  161ad5:	c5 f8 28 4d d0       	vmovaps -0x30(%rbp),%xmm1
  161ada:	ba 10 24 00 00       	mov    $0x2410,%edx
  161adf:	4c 89 f6             	mov    %r14,%rsi
  161ae2:	c5 f8 29 03          	vmovaps %xmm0,(%rbx)
  161ae6:	c5 f8 29 4b 10       	vmovaps %xmm1,0x10(%rbx)
  161aeb:	48 83 c3 20          	add    $0x20,%rbx
  161aef:	48 89 df             	mov    %rbx,%rdi
  161af2:	e8 99 65 0d 00       	call   238090 <memcpy>
  161af7:	48 81 c4 58 6c 00 00 	add    $0x6c58,%rsp
  161afe:	5b                   	pop    %rbx
  161aff:	41 5e                	pop    %r14
  161b01:	41 5f                	pop    %r15
  161b03:	5d                   	pop    %rbp
  161b04:	c3                   	ret

Disassembly of section .plt:
