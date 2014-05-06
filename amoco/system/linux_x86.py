# This code is part of Amoco
# Copyright (C) 2006-2011 Axel Tillequin (bdcht3@gmail.com) 
# published under GPLv2 license

from amoco.system.core import *
from amoco.code import tag

import amoco.arch.x86.cpu_x86 as cpu

PAGESIZE = 4096

class ELF(CoreExec):

    def __init__(self,p):
        CoreExec.__init__(self,p,cpu)

    # load the program into virtual memory (populate the mmap dict)
    def load_binary(self):
        p = self.bin
        if p!=None:
            # create text and data segments according to elf header:
            for s in p.Phdr:
                ms = p.loadsegment(s,PAGESIZE)
                if ms!=None:
                    vaddr,data = ms.popitem()
                    self.mmap.write(vaddr,data)
            # create the dynamic segments:
            self.load_shlib()
        # create the stack zone:
        self.mmap.newzone(cpu.esp)

    # call dynamic linker to populate mmap with shared libs:
    # for now, the external libs are seen through the elf dynamic section:
    def load_shlib(self):
        for k,f in self.bin._Elf32__dynamic(None).iteritems():
            self.mmap.write(k,cpu.ext(f))

    # lookup in bin if v is associated with a function or variable name:
    def check_sym(self,v):
        if v._is_cst:
            x = self.bin.functions.get(v.value,None) or self.bin.variables.get(v.value,None)
            if x is not None:
                if isinstance(x,str): x=cpu.ext(x)
                else: x=cpu.sym(x[0],v.value,v.size)
                return x
        return None

    def initenv(self):
        from amoco.cas.mapper import mapper
        m = mapper()
        for k,v in ((cpu.eip, cpu.cst(self.bin.entrypoint(),32)),
                    (cpu.ebp, cpu.cst(0,32)),
                    (cpu.eax, cpu.cst(0,32)),
                    (cpu.ebx, cpu.cst(0,32)),
                    (cpu.ecx, cpu.cst(0,32)),
                    (cpu.edx, cpu.cst(0,32)),
                    (cpu.esi, cpu.cst(0,32)),
                    (cpu.edi, cpu.cst(0,32))):
            m[k] = v
        return m

    def PC(self): return self.cpu.eip

    def codehelper(self,**kargs):
        if 'seq' in kargs: return self.seqhelper(kargs['seq'])
        if 'block' in kargs: return self.blockhelper(kargs['block'])
        if 'func' in kargs: return self.funchelper(kargs['func'])


    # seqhelper provides arch-dependent information to amoco.main classes
    def seqhelper(self,seq):
        for i in seq:
            # some basic hints:
            if i.mnemonic.startswith('RET'):
                i.misc[tag.FUNC_END]=1
                continue
            elif i.mnemonic == 'PUSH':
                i.misc[tag.FUNC_STACK]=1
                if i.operands[0] is cpu.ebp:
                    i.misc[tag.FUNC_START]=1
                    continue
            elif i.mnemonic == 'POP':
                i.misc[tag.FUNC_UNSTACK]=1
                if i.operands[0] is cpu.ebp:
                    i.misc[tag.FUNC_END]=1
                    continue
            # provide hints of absolute location from relative offset:
            elif i.mnemonic in ('CALL','JMP','Jcc'):
                if i.mnemonic == 'CALL':
                    i.misc[tag.FUNC_CALL]=1
                    i.misc['retto'] = i.address+i.length
                if (i.address is not None) and i.operands[0]._is_cst:
                    v = i.address+i.operands[0].signextend(32)+i.length
                    x = self.check_sym(v)
                    if x is not None: v=x
                    i.misc['to'] = v
                    continue
            # check operands (globals & .got calls):
            for op in i.operands:
                if op._is_mem:
                    if op.a.base is cpu.ebp:
                        if op.a.disp<0: i.misc[tag.FUNC_ARG]=1
                        else: i.misc[tag.FUNC_VAR]=1
                    elif op.a.base._is_cst:
                        x = self.check_sym(op.a.base)
                        if x is not None: op.a.base=x
                elif op._is_cst:
                    x = self.check_sym(op)
                    i.misc['imm_ref'] = x
        return seq

    def blockhelper(self,block):
        for i in self.seqhelper(block.instr):
            block.misc.update(i.misc)
        # compute mapper:
        m = block.map
        # annotations based on block semantics:
        sta,sto = block.support
        if m[cpu.mem(cpu.ebp-4,32)] == cpu.ebp:
            block.misc[tag.FUNC_START]=1
        if m[cpu.eip]==cpu.mem(cpu.esp-4,32):
            block.misc[tag.FUNC_END]=1
        if m[cpu.mem(cpu.esp,32)]==sto:
            block.misc[tag.FUNC_CALL]=1
        return block


# HOOKS DEFINED HERE :
#----------------------------------------------------------------------------

@stub_default
def pop_eip(m):
    cpu.pop(m,cpu.eip)

@stub
def __libc_start_main(m):
    m[cpu.eip] = m(cpu.mem(cpu.esp+4,32))
    cpu.push(m,cpu.ext('exit'))

@stub
def exit(m):
    m[cpu.eip] = top(32)
@stub
def abort(m):
    m[cpu.eip] = top(32)
@stub
def __assert(m):
    m[cpu.eip] = top(32)
@stub
def __assert_fail(m):
    m[cpu.eip] = top(32)
@stub
def _assert_perror_fail(m):
    m[cpu.eip] = top(32)

#----------------------------------------------------------------------------

# SYSCALLS:
#----------------------------------------------------------------------------
IDT={
   1: "exit",
   2: "fork",
   3: "read",
   4: "write",
   5: "open",
   6: "close",
   7: "waitpid",
   8: "creat",
   9: "link",
  10: "unlink",
  11: "execve",
  12: "chdir",
  13: "time",
  14: "mknod",
  15: "chmod",
  16: "lchown",
  17: "break",
  18: "oldstat",
  19: "lseek",
  20: "getpid",
  21: "mount",
  22: "umount",
  23: "setuid",
  24: "getuid",
  25: "stime",
  26: "ptrace",
  27: "alarm",
  28: "oldfstat",
  29: "pause",
  30: "utime",
  31: "stty",
  32: "gtty",
  33: "access",
  34: "nice",
  35: "ftime",
  36: "sync",
  37: "kill",
  38: "rename",
  39: "mkdir",
  40: "rmdir",
  41: "dup",
  42: "pipe",
  43: "times",
  44: "prof",
  45: "brk",
  46: "setgid",
  47: "getgid",
  48: "signal",
  49: "geteuid",
  50: "getegid",
  51: "acct",
  52: "umount2",
  53: "lock",
  54: "ioctl",
  55: "fcntl",
  56: "mpx",
  57: "setpgid",
  58: "ulimit",
  59: "oldolduname",
  60: "umask",
  61: "chroot",
  62: "ustat",
  63: "dup2",
  64: "getppid",
  65: "getpgrp",
  66: "setsid",
  67: "sigaction",
  68: "sgetmask",
  69: "ssetmask",
  70: "setreuid",
  71: "setregid",
  72: "sigsuspend",
  73: "sigpending",
  74: "sethostname",
  75: "setrlimit",
  76: "getrlimit",
  77: "getrusage",
  78: "gettimeofday",
  79: "settimeofday",
  80: "getgroups",
  81: "setgroups",
  82: "select",
  83: "symlink",
  84: "oldlstat",
  85: "readlink",
  86: "uselib",
  87: "swapon",
  88: "reboot",
  89: "readdir",
  90: "mmap",
  91: "munmap",
  92: "truncate",
  93: "ftruncate",
  94: "fchmod",
  95: "fchown",
  96: "getpriority",
  97: "setpriority",
  98: "profil",
  99: "statfs",
100: "fstatfs",
101: "ioperm",
102: "socketcall",
103: "syslog",
104: "setitimer",
105: "getitimer",
106: "stat",
107: "lstat",
108: "fstat",
109: "olduname",
110: "iopl",
111: "vhangup",
112: "idle",
113: "vm86old",
114: "wait4",
115: "swapoff",
116: "sysinfo",
117: "ipc",
118: "fsync",
119: "sigreturn",
120: "clone",
121: "setdomainname",
122: "uname",
123: "modify_ldt",
124: "adjtimex",
125: "mprotect",
126: "sigprocmask",
127: "create_module",
128: "init_module",
129: "delete_module",
130: "get_kernel_syms",
131: "quotactl",
132: "getpgid",
133: "fchdir",
134: "bdflush",
135: "sysfs",
136: "personality",
137: "afs_syscall",
138: "setfsuid",
139: "setfsgid",
140: "_llseek",
141: "getdents",
142: "_newselect",
143: "flock",
144: "msync",
145: "readv",
146: "writev",
147: "getsid",
148: "fdatasync",
149: "_sysctl",
150: "mlock",
151: "munlock",
152: "mlockall",
153: "munlockall",
154: "sched_setparam",
155: "sched_getparam",
156: "sched_setscheduler",
157: "sched_getscheduler",
158: "sched_yield",
159: "sched_get_priority_max",
160: "sched_get_priority_min",
161: "sched_rr_get_interval",
162: "nanosleep",
163: "mremap",
164: "setresuid",
165: "getresuid",
166: "vm86",
167: "query_module",
168: "poll",
169: "nfsservctl",
170: "setresgid",
171: "getresgid",
172: "prctl",
173: "rt_sigreturn",
174: "rt_sigaction",
175: "rt_sigprocmask",
176: "rt_sigpending",
177: "rt_sigtimedwait",
178: "rt_sigqueueinfo",
179: "rt_sigsuspend",
180: "pread64",
181: "pwrite64",
182: "chown",
183: "getcwd",
184: "capget",
185: "capset",
186: "sigaltstack",
187: "sendfile",
188: "getpmsg",
189: "putpmsg",
190: "vfork",
191: "ugetrlimit",
192: "mmap2",
193: "truncate64",
194: "ftruncate64",
195: "stat64",
196: "lstat64",
197: "fstat64",
198: "lchown32",
199: "getuid32",
200: "getgid32",
201: "geteuid32",
202: "getegid32",
203: "setreuid32",
204: "setregid32",
205: "getgroups32",
206: "setgroups32",
207: "fchown32",
208: "setresuid32",
209: "getresuid32",
210: "setresgid32",
211: "getresgid32",
212: "chown32",
213: "setuid32",
214: "setgid32",
215: "setfsuid32",
216: "setfsgid32",
217: "pivot_root",
218: "mincore",
219: "madvise",
219: "madvise1",
220: "getdents64",
221: "fcntl64",
224: "gettid",
225: "readahead",
226: "setxattr",
227: "lsetxattr",
228: "fsetxattr",
229: "getxattr",
230: "lgetxattr",
231: "fgetxattr",
232: "listxattr",
233: "llistxattr",
234: "flistxattr",
235: "removexattr",
236: "lremovexattr",
237: "fremovexattr",
238: "tkill",
239: "sendfile64",
240: "futex",
241: "sched_setaffinity",
242: "sched_getaffinity",
243: "set_thread_area",
244: "get_thread_area",
245: "io_setup",
246: "io_destroy",
247: "io_getevents",
248: "io_submit",
249: "io_cancel",
250: "fadvise64",
252: "exit_group",
253: "lookup_dcookie",
254: "epoll_create",
255: "epoll_ctl",
256: "epoll_wait",
257: "remap_file_pages",
258: "set_tid_address",
259: "timer_create",
260: "timer_settime",
261: "timer_gettime",
262: "timer_getoverrun",
263: "timer_delete",
264: "clock_settime",
265: "clock_gettime",
266: "clock_getres",
267: "clock_nanosleep",
268: "statfs64",
269: "fstatfs64",
270: "tgkill",
271: "utimes",
272: "fadvise64_64",
273: "vserver" }
