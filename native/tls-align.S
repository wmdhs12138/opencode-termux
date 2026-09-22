/* Force PT_TLS.p_align to Android's required AArch64 minimum. */
    .section .tbss.opencode_termux,"awTR",@nobits
    .p2align 6
    .hidden opencode_termux_tls_alignment_anchor
    .type opencode_termux_tls_alignment_anchor, %object
    .size opencode_termux_tls_alignment_anchor, 1
opencode_termux_tls_alignment_anchor:
    .zero 1
