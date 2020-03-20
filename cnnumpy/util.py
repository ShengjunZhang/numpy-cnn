import numpy as np
from time import time
try: from numba import njit
except: njit = None

if njit is None: print('install numba can double speed!')

def neighbors(shape, core, offset=0):
    shp = [slice(0,i) for i in core]
    idx = np.mgrid[tuple(shp)]
    idx = idx.reshape((len(core),-1))
    offset = np.array(core)//2*offset
    idx -= offset.reshape((-1,1))
    acc = np.cumprod((1,)+shape[::-1][:-1])
    return np.dot(idx.T, acc[::-1])

def jit_fill_col(pdimg, idx, colimg):
    s = 0
    for i in range(len(pdimg)):
        if pdimg[i]&1==0: continue
        for j in idx:
            colimg[s] = pdimg[i+j]
            s += 1
    return colimg

def fill_col(pdimg, idx, colimg):
    rc = np.where(pdimg&1)[0]
    rc = rc.reshape((-1,1))+idx
    colimg[:] = pdimg[rc.ravel()]
    return colimg

if not njit is None: fill_col = njit(jit_fill_col)

def conv(img, core, stride=(1,1), buf=['']):
    # new the col_img, if needed
    strh, strw = stride
    cimg_w = np.cumprod(core.shape[1:])[-1]
    n,c,h,w = img.shape
    cimg_h = n*(h//strh)*(w//strw)
    if len(buf[0])<cimg_h*cimg_w:
        col_img = np.zeros(cimg_h*cimg_w, dtype=np.int32)
        buf[0] =  col_img
    else:
        col_img = buf[0][:cimg_h*cimg_w]
        col_img[:] = 0
    # mark where need
    iimg = img.view(dtype=np.int32)
    iimg &= 0xfffffffe
    iimg[:,0,::strh,::strw] |= 1
    # ravel the image
    n,c,h,w = np.array(core.shape)
    shp = ((0,0),(0,0),(h//2,h//2),(w//2,w//2))
    pdimg = np.pad(iimg, shp, 'constant', constant_values=0)
    nbs = neighbors(pdimg.shape[1:], core.shape[1:], (0,1,1))
    fill_col(pdimg.ravel(), nbs, col_img)
    col_img = col_img.view(np.float32)
    col_img = col_img.reshape((cimg_h, cimg_w))
    # dot
    col_core = core.reshape((core.shape[0],-1))
    rst = col_core.dot(col_img.T)
    ni, ci, hi, wi = img.shape
    return rst.reshape((ni, n, hi//strh, wi//strw))


def jit_fill_max(pdimg, idx, colimg):
    s = 0
    for i in range(len(pdimg)):
        if pdimg[i]&1==0: continue
        for j in idx:
            colimg[s] = max(colimg[s], pdimg[i+j])
        s += 1
    return colimg

def fill_max(pdimg, idx, colimg):
    rc = np.where(pdimg&1)[0]
    rc = rc.reshape((-1,1))+idx
    vs = pdimg[rc.ravel()].reshape((-1, len(idx)))
    np.max(vs, axis=-1, out=colimg)

if not njit is None: fill_max = njit(jit_fill_max)

def maxpool(img, stride=(2,2)):
    strh, strw = stride
    n,c,h,w = img.shape
    cimg_h = n*c*(h//strh)*(w//strw)
    
    iimg = img.view(dtype=np.int32)
    iimg &= 0xfffffffe
    iimg[:,:,::strh,::strw] |= 1
    
    nbs = neighbors(img.shape[1:], (1,)+stride)
    shp = (n, c, h//strh, w//strw)
    colimg = np.zeros(shp, dtype=np.int32)
    fill_max(iimg.ravel(), nbs, colimg.ravel())
    return colimg.view(np.float32)

def jit_resize(img, k, ra, rb, rs, _rs, ca, cb, cs, _cs, out):
    h, w = img.shape
    for r in range(h*k):
        rar = ra[r]
        rbr = rar+1
        rsr = rs[r]
        _rsr = _rs[r]
        for c in range(w*k):
            cac = ca[c]
            cbc = cac+1
            rra = img[rar,cac]*_rsr
            rra += img[rbr,cac]*rsr
            rrb = img[rar,cbc]*_rsr
            rrb += img[rbr,cbc]*rsr
            rcab = rra * _cs[c] + rrb * cs[c]
            out[r,c] = rcab

def resize(img, k, ra, rb, rs, _rs, ca, cb, cs, _cs, out):
    out[:img.shape[0]] = img[:,ca]*_cs + img[:,cb]*cs
    out[:] = (out[ra].T*_rs + out[rb].T*rs).T
    
if not njit is None: resize = njit(jit_resize)

def upsample(img, k, out=None):
    nc, (h, w) = img.shape[:-2], img.shape[-2:]
    if out is None:
        out = np.zeros(nc+(h*k, w*k), dtype=img.dtype)
    rs = np.linspace(-0.5+0.5/k, h-0.5-0.5/k, h*k, dtype=np.float32)
    cs = np.linspace(-0.5+0.5/k, w-0.5-0.5/k, w*k, dtype=np.float32)
    np.clip(rs, 0, h-1, out=rs)
    np.clip(cs, 0, w-1, out=cs)
    ra = np.floor(rs).astype(np.uint32)
    ca = np.floor(cs).astype(np.uint32)
    np.clip(ra, 0, h-1.5, out=ra)
    np.clip(ca, 0, w-1.5, out=ca)
    rs -= ra; cs -= ca; 
    outcol = out.reshape((-1, h*k, w*k))
    imgcol = img.reshape((-1, h, w))
    for i, o in zip(imgcol, outcol):
        resize(i, k, ra, ra+1, rs, 1-rs, ca, ca+1, cs, 1-cs, o)
    return out

if __name__ == '__main__':
    from skimage.data import camera
    import matplotlib.pyplot as plt
    from scipy.ndimage import convolve
    img = np.zeros((1, 3, 512, 512), dtype=np.float32)
    #img.ravel()[:] = np.arange(3*512*512)
    core = np.zeros((32, 3, 3, 3), dtype=np.float32)
    #core.ravel()[:] = np.arange(3*3*3*32)

    rst1 = conv(img, core, (1,1))
    start = time()
    rst1 = conv(img, core, (1,1))
    print('jit cost:', time()-start)

    start = time()
    rst2 = conv(img, core, (1,1))
    print('numpy cost:', time()-start)