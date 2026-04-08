{ pkgs }: {
  deps = [
    pkgs.python310
    pkgs.python310Packages.pip
    pkgs.libgcc
    pkgs.stdenv.cc.cc.lib  # libstdc++ — needed by scikit-learn/numpy
    pkgs.zlib
  ];
}
