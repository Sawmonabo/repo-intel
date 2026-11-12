"""Linux-only subprocess launcher; RLIMIT_AS is address space, not resident RAM."""
import os
import sys

def main():
    import resource
    amount=int(sys.argv[1])*1024*1024
    resource.setrlimit(resource.RLIMIT_AS,(amount,amount))
    args=sys.argv[3:]
    os.execvpe(args[0],args,os.environ.copy())

if __name__=='__main__':main()
