# 纯标准库实现，不需要任何 pip 依赖 —— 镜像因此可以非常小、构建也不需要联网装包
FROM python:3.12-alpine

# 版本号不写死在 Dockerfile 里：CI 把镜像 tag 作为 build-arg 传进来
# （本地 docker build 不带参数时标签是 "local"）。曾经的写法是直接把
# "1.2.8" 写进 LABEL，结果 1.2.9 / 1.3.0 两次发版都漏改，docker inspect
# 看到的版本永远落后 —— 少一个手工同步点就少一个出错的地方。
ARG APP_VERSION=local

LABEL org.opencontainers.image.title="HiRouterCenter" \
      org.opencontainers.image.description="华为路由器控制中心：IPv6 防火墙同步、设备管理与计划任务，含通知推送" \
      org.opencontainers.image.version="${APP_VERSION}"

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONFAULTHANDLER=1 \
    PYTHONIOENCODING=utf-8 \
    LANG=C.UTF-8 \
    TZ=Asia/Shanghai \
    SESSION_FILE=/data/session.json \
    SETTINGS_FILE=/data/settings.json \
    HEALTH_PORT=8099 \
    HEALTH_HOST=127.0.0.1 \
    PORT=6600

WORKDIR /app

# 非 root 运行
RUN addgroup -g 10001 -S syncapp \
 && adduser -u 10001 -S -G syncapp -H -s /sbin/nologin syncapp \
 && mkdir -p /data \
 && chown -R syncapp:syncapp /data

COPY app/ /app/app/
RUN chown -R syncapp:syncapp /app

USER syncapp

VOLUME ["/data"]
# 6600 = 浏览器控制台（PORT>0 就监听；PORT=0 才关）。
# 健康检查/状态（8099）只绑 127.0.0.1（见 HEALTH_HOST），只有容器自己和宿主机
# 本机能访问 —— 不是对外服务，所以**不 EXPOSE**，免得 NAS 面板把它当成可发布端口。
EXPOSE 6600

# 健康检查：/healthz 会在「最近一轮同步成功」时返回 200
# 先设 no_proxy=*：NAS 上的 Docker 若配了代理，会以 HTTP_PROXY 注入容器，那样
# urllib 连 127.0.0.1 都会绕到代理去 —— 健康检查会永远失败（假 unhealthy）。
HEALTHCHECK --interval=60s --timeout=6s --start-period=25s --retries=3 \
  CMD python -c "import os,sys,urllib.request; \
os.environ['no_proxy']='*'; \
p=os.environ.get('HEALTH_PORT','8099'); \
sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:'+p+'/healthz', timeout=4).status==200 else 1)"

ENTRYPOINT ["python", "-u", "-m", "app.main"]
