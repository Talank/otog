# Mechanism 8: AsyncHttpClient cached Netty leak-detection policy.
# NettyLeakDetectorExtension sets io.netty.leakDetection.level=paranoid; whichever class
# initializes ResourceLeakDetector first pins the policy for the whole fork.
MECHANISM="ahc-leak"
NATURAL="ahc.natural"
TRACK="org.asynchttpclient.request.body.multipart.MultipartBodyTest org.asynchttpclient.netty.NettyConnectionResetByPeerTest"
# Exact pair from mechanisms.md section 8 (10-pair median 35.58% lower for fast).
PAIR_FAST="org.asynchttpclient.request.body.multipart.MultipartBodyTest org.asynchttpclient.netty.NettyConnectionResetByPeerTest"
PAIR_SLOW="org.asynchttpclient.netty.NettyConnectionResetByPeerTest org.asynchttpclient.request.body.multipart.MultipartBodyTest"
# Whole-suite: natural has ResetByPeer (pos 46) before MultipartBody (pos 73), so the natural
# order runs the buffer consumer under PARANOID. Fast arm pushes the policy producer to the end.
WHOLE_FAST_MOVES="back:org.asynchttpclient.netty.NettyConnectionResetByPeerTest"
WHOLE_SLOW_MOVES=""
