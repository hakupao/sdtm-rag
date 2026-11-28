"""公开部署预检: 这个镜像够不够格放到隧道后面 (P3.4 的「镜像下限」)。只用标准库和镜像里的 server.auth。

deploy/ 不进镜像, 所以经标准输入送进去, 在要部署的镜像里跑:

    out=$(docker run --rm -i --entrypoint python <镜像> - < deploy/public-net/image_floor_check.py) \
      && [ "$out" = "image-floor: ok" ] || { echo "镜像下限预检未通过"; exit 1; }

合格 = 退出码 0 **并且**标准输出恰好是 `image-floor: ok`。两样都要核对: docker run 漏写 -i 时容器拿不到标准输入,
python 读到空脚本, 什么都不做就以 0 退出 —— 只看退出码的话, 任何镜像都会被放行。
不合格时退出码非 0, 原因在标准错误里。P3.4 之前的镜像没有 PUBLIC_EDGE_LEVEL 这个属性, 在第一条判断就被拒。标记是镜像自己声明的, 所以再实际调一次「可信代理必须是单主机」的检查: 标记在而实现不在也拒。
server.auth 不读 .env、不碰数据目录, 这段脚本不需要任何环境变量或挂载。
"""
import sys

from server import auth

if getattr(auth, "PUBLIC_EDGE_LEVEL", 0) < 1:
    sys.exit("image predates P3.4 (public edge): no server.auth.PUBLIC_EDGE_LEVEL >= 1")
try:
    auth._check_public_trusted("10.201.8.0/24")
except RuntimeError:
    print("image-floor: ok")
    sys.exit(0)
sys.exit("PUBLIC_EDGE_LEVEL is set, but a trusted-proxy network wider than one host is accepted")
