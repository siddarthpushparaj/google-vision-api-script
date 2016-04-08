#!/usr/bin/env python

import argparse
import base64

from PIL import Image
from PIL import ImageDraw

from googleapiclient import discovery
import httplib2
from oauth2client.client import GoogleCredentials


import pprint
import os
import json
import subprocess

# Task feature dictionaries
MAX_RESULTS = 10
features = {}
features['face_detection'] = {'type': 'FACE_DETECTION', 'maxResults': MAX_RESULTS}
features['landmark_detection'] = {'type': 'LANDMARK_DETECTION', 'maxResults': MAX_RESULTS}
features['logo_detection'] = {'type': 'LOGO_DETECTION', 'maxResults': MAX_RESULTS}
features['label_detection'] = {'type': 'LABEL_DETECTION', 'maxResults': MAX_RESULTS}
features['ocr'] = {'type': 'TEXT_DETECTION', 'maxResults': MAX_RESULTS}
features['safe_search'] = {'type': 'SAFE_SEARCH_DETECTION', 'maxResults': MAX_RESULTS}
features['properties'] = {'type': 'IMAGE_PROPERTIES', 'maxResults': MAX_RESULTS}



# [START get_vision_service]
DISCOVERY_URL='https://{api}.googleapis.com/$discovery/rest?version={apiVersion}'


def get_vision_service():
    credentials = GoogleCredentials.get_application_default()
    return discovery.build('vision', 'v1', credentials=credentials,
                           discoveryServiceUrl=DISCOVERY_URL)
# [END get_vision_service]

# [START highlight_faces]
def highlight_faces(image, faces, output_filename):
    """Draws a polygon around the faces, then saves to output_filename.

    Args:
      image: a file containing the image with the faces.
      faces: a list of faces found in the file. This should be in the format
          returned by the Vision API.
      output_filename: the name of the image file to be created, where the faces
          have polygons drawn around them.
    """
    image.seek(0)
    im = Image.open(image)
    draw = ImageDraw.Draw(im)

    if faces:
        for face in faces:
            box = [(v.get('x', 0.0), v.get('y', 0.0)) for v in face['fdBoundingPoly']['vertices']]
            draw.line(box + [box[0]], width=5, fill='#00ff00')

    del draw
    im.save(output_filename)
# [END highlight_faces]


def draw_rectangle(draw, response, item_str, color='#00ff00', index_str='boundingPoly'):
    items = response['responses'][0].get(item_str, None)
    if items:
        for item in items:
            box = [(v.get('x', 0.0), v.get('y', 0.0)) for v in item[index_str]['vertices']]
            draw.line(box + [box[0]], width=5, fill=color)
    
def highlight_image(image, response, output_folder, tasks):
    image.seek(0)
    im = Image.open(image)
    draw = ImageDraw.Draw(im)

    if 'all' in tasks or 'face_detection' in tasks:
        draw_rectangle(draw, response, 'faceAnnotations', '#00ff00', 'fdBoundingPoly')
    if 'all' in tasks or 'landmark_detection' in tasks:
        draw_rectangle(draw, response, 'landmarkAnnotations', '#7cedff')
    if 'all' in tasks or 'logo_detection' in tasks:
        draw_rectangle(draw, response, 'logoAnnotations', '#ff00ff')
    if 'all' in tasks or 'ocr' in tasks:
        draw_rectangle(draw, response, 'textAnnotations', '#0000ff')

    del draw
    im.save(output_folder + '/edited_image.jpg')


def log_metadata(response, output_folder):
    json.dump(response, open(output_folder + '/all.json', 'w'))
    data = {}
    data['labels'] = [x['description'] for x in response['responses'][0].get('labelAnnotations', [])]
    data['faces'] = len(response['responses'][0].get('faceAnnotations', []))
    data['landmarks'] = [x['description'] for x in response['responses'][0].get('landmarkAnnotations', [])]
    data['logos'] = [x['description'] for x in response['responses'][0].get('logoAnnotations', [])]
    data['primary_text'] = [x['description'] for x in response['responses'][0].get('textAnnotations', [{'description':''}])][0]
    json.dump(data, open(output_folder + '/selective.json', 'w'))

def process_image(image_file, service, output_file_path, tasks=['all']):
    if image_file.split('.')[-1].lower() not in ['jpg', 'jpeg', 'png']:
        print "Can't operate on this file extension... Giving up"
        return
    max_results = 10
    with open(image_file, 'rb') as image:
        _features = []
        if 'all' in tasks:
            _features = [v for k,v in features.items()]
        else:
            for task in tasks:
                _features.append(features[task])
        image_content = image.read()
        batch_request = [{
            'image': {
                'content': base64.b64encode(image_content).decode('UTF-8')
            },
            'features': _features
        }]
        

        request = service.images().annotate(body={'requests': batch_request})
        response = request.execute()
        # pprint.pprint(response)
        
        output_folder = output_file_path + '/_processed_image_' + ''.join(image_file.split('/')[-1].split('.')[:-1])
        print "Analysis results in folder: ", output_folder
        if not os.path.exists(output_folder):
            os.makedirs(output_folder)
        
        log_metadata(response, output_folder)
        highlight_image(image, response, output_folder, tasks)

def process_video(video_file, service, output_file_path, tasks=['all']):
    # Sample video and dispatch image file. 
    output_folder = output_file_path + '/_processed_video_' + ''.join(video_file.split('/')[-1].split('.')[:-1])
    if not os.path.exists(output_folder):
        os.makedirs(output_folder)
    cmd = 'ffmpeg -i '+ video_file + ' -r 2 -q:v 2 '+ output_folder + '/image-%d.jpeg'
    subprocess.call(cmd, shell=True)
    for path in os.listdir(output_folder):
        input_file_path = output_folder + '/' + path
        if os.path.isfile(input_file_path):
            dispatch_file(input_file_path, service, output_folder)

def dispatch_file(input_file_path, service, output_file_path, tasks=['all']):
    print "processing file: ", input_file_path
    file_ext = input_file_path.split('.')[-1].lower()
    if file_ext in ['jpg', 'jpeg', 'png']:
        process_image(input_file_path, service, output_file_path)
    elif file_ext in ['mp4']:
        process_video(input_file_path, service, output_file_path)
    else:
        print "Can't operate on this file extension... Giving up"
        

def main(input_file_path, output_file_path):
    service = get_vision_service()
    if os.path.isfile(input_file_path):
        dispatch_file(input_file_path, service, output_file_path)
    elif os.path.isdir(input_file_path):
        print 'processing folder: ', input_file_path
        for path in os.listdir(input_file_path):
            input_file = input_file_path + '/' + path
            if os.path.isfile(input_file):
                dispatch_file(input_file, service, output_file_path)
    
if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description='Detects Vision API routines on the given image or video. If it is a video, samples two images per second. ')
    parser.add_argument(
        'input_path', help='the image you\'d like to detect faces in.')
    parser.add_argument(
        '--out', dest='output', default=os.getcwd(),
        help='the name of the output file.')
    args = parser.parse_args()

    main(args.input_path, args.output)
