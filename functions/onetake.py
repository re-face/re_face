from __future__ import absolute_import
import functions.DBface as DBFace
import functions.segment as segment
import functions.FEGAN as FEGAN
import functions.APDrawingGan as APDrawingGAN
from functions.dependency_imports import *
import re_face_preprocessing.CropFace as cropface
import re_face_preprocessing.FaceSwapByMask as faceswapbymask
import re_face_preprocessing
import glob


def sketch_image(imagename, foldername='data/rebuild/', savefoldername='data/sketch/', landmarkdir='/data/landmark/', maskdir='/data/segment/'):
    APDrawingGAN.APDrawingGan(foldername, savefoldername,
                              imagename, os.getcwd()+landmarkdir, os.getcwd()+maskdir)


def remove_presketch(originsketch):
    for filename in os.listdir('sketch/'):
        if originsketch in filename:
            os.remove('sketch/'+filename)


def make_segment(originimageread, imagepath):
    segment.segment(originimageread, imagepath)


def do_fegan(mask, sketch, stroke, originimageread, read):
    # already read files
    FEGAN.execute_FEGAN(mask, sketch, stroke, image=originimageread, read=read)


def save_image_to_gcs(user_code, mode_type, originname, originfile):
    blobfile = STORAGE_CLIENT.bucket(GS_BUCKET_NAME).blob(
        'user_' + user_code + '/' + mode_type + '/' + originname).upload_from_filename(originfile)
    return 1


def load_image_from_gcs(user_code, mode_type, originname):
    blobfile = STORAGE_CLIENT.bucket(GS_BUCKET_NAME).blob(
        str('user_' + user_code + '/' + mode_type + '/' + originname))
    if blobfile.exists():
        blobfile.download_to_filename(
            'data/'+mode_type+'/'+originname)
        return 1
    return 404


def load_images_from_gcs(user_code, mode_type):
    blobfile = STORAGE_CLIENT.list_blobs(GS_BUCKET_NAME,
        prefix=str('user_' + user_code + '/' + mode_type+'/'))
    for blob in blobfile:
        filename = blob.name.replace('/', '_')
        blob.download_to_filename(
            'data/'+mode_type+'/' + user_code+"_"+filename)  # Download
    return 404


def remove_image_from_local(mode_type, user_code, originname, all=False):
    if all:
        for fol in ['originimage','recover','result','average', 'detect_results', 'input', 'landmark', 'segment', 'mask', 'stroke', 'rebuild', 'sketch', 'origin']:
            files = glob.glob('data/'+fol+'/*')
            for f in files:
                if str(user_code) in f:
                    os.remove(f)
        pass
    else:
        os.remove('data/'+mode_type+'/'+str(user_code)+'_'+originname)
        pass
    return 1


def preprocess(user_code, rebuildimage_rcv, originimages_rcv, fmask_rcv, stroke_rcv, origin_flag):
    # rebuildimages -> to be fixed
    # originimages -> original images
    remove_image_from_local('',str(user_code),'',all=True)
    reqstring = ''.join(random.choice(
        string.ascii_uppercase + string.digits) for _ in range(3))
    userimage = str(user_code)+reqstring+'.png'
    rebuildimage = rebuildimage_rcv.convert('RGB')
    rebuildimage.save('data/input/'+userimage)
    # origin_flag -> get from request-> default
    # 1-> all from gcs and request
    # 2-> only from request

    originimages_cvt = []
    for oneimage in originimages_rcv:
        imagename = oneimage.name
        oneimage = Image.open(oneimage).convert('RGB')
        oneimage.save('data/'+"originimage/"+str(user_code)+imagename)
        save_image_to_gcs(str(user_code),'originimage',str(user_code)+imagename,'data/originimage/'+str(user_code)+imagename)

    if int(origin_flag) == 1:
        # gcs download
        load_images_from_gcs(str(user_code), 'originimage')

    files = glob.glob('data/'+"originimage"+'/*')
    for f in files:
        if str(user_code) in f:
            originimages_cvt.append(cv2.imread(f))
    fmask = fmask_rcv.convert('RGB')
    fmask.save('data/mask/'+userimage)
    fmaskread = cv2.imread('data/mask/'+userimage)
    save_image_to_gcs(str(user_code),'mask',userimage,'data/mask/'+userimage)
    croppedimg, averageimg, points, landmarks, fmask = cropface.crop_and_average(
        rebuildimage, originimages_cvt, np.array(fmaskread).copy(), save_file=False, _pil=True)
    swappedface = faceswapbymask.pil_preprocessing(
        averageimg, croppedimg, np.array(fmaskread).copy())
    # cv2.imwrite('swappedface.png',swappedface)
    cv2.imwrite('data/origin/'+userimage, swappedface)
    cv2.imwrite('data/rebuild/'+userimage, croppedimg)
    cv2.imwrite('data/average/'+userimage, averageimg)

    with open("data/landmark/{}.txt".format(str(user_code)+reqstring), "w") as f:
        for point in points:
            text = str(point[0])+' '+str(point[1])+'\n'
            f.write(text)

    inputimage = cv2.imread('data/input/'+userimage)
    originimageread_pil = Image.open('data/origin/'+userimage)
    save_image_to_gcs(str(user_code), 'origin',
                      userimage, 'data/origin/'+userimage)
    make_segment(originimageread_pil, 'data/segment/'+userimage)
    sketch_image(userimage, foldername='data/origin/')
    sketch = cv2.imread('data/sketch/'+userimage)
    save_image_to_gcs(str(user_code), 'sketch',
                      userimage, 'data/sketch/'+userimage)

    rebuildimg, rebuilt = FEGAN.execute_FEGAN(
        fmaskread, sketch, stroke_rcv, userimage, image=np.array(croppedimg).copy(), read=False)
    rebuilt = cv2.imread('data/result/'+userimage)
    fmaskread = cv2.imread('data/mask/'+userimage)
    recov_img, newmask = cropface.rotate_scale_origin(
        inputimage, rebuilt, fmaskread, landmarks)
    cv2.imwrite('data/recover/'+userimage, recov_img)

    save_image_to_gcs(str(user_code), 'input',
                      userimage, 'data/input/'+userimage)
    save_image_to_gcs(str(user_code), 'rebuild',
                      userimage, 'data/rebuild/'+userimage)
    save_image_to_gcs(str(user_code), 'average',
                      userimage, 'data/average/'+userimage)
    save_image_to_gcs(str(user_code), 'recover',
                      userimage, 'data/recover/'+userimage)
    save_image_to_gcs(str(user_code), 'result', userimage, rebuildimg)
#    remove_image_from_local('', user_code, '', all=True)
    with open('data/recover/'+userimage, "rb") as f:
        return HttpResponse(f.read(), content_type="image/png")
