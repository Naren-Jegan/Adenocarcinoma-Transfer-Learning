from PIL import Image, ImageChops, ImageStat
import openslide
from os.path import join, exists, isdir
from os import listdir, makedirs
import pickle
from shutil import move
from time import sleep
import argparse
import concurrent.futures
import multiprocessing
import random
import numpy as np

#count cores for parallel processing
core_count = multiprocessing.cpu_count()

#options
parser = argparse.ArgumentParser(description='Uses probabilities found by probability_finder.py to generate probability heat map fpr WSIs')
parser.add_argument('data_path', metavar='data-path', help='Path to data directory where slide images are present', type=str)
parser.add_argument('model_dir', metavar='model-dir', help='Path to model directory to obtain probability.pickle', type=str)
parser.add_argument('-p', '--patch-size', help='Default value is 512. Other choices are 256 and 1024. ', nargs='?', type=int, const=512, default=512, choices=[256, 512, 1024])
args = parser.parse_args()

# basic settings
main_dir = args.data_path
pickle_file = join(args.model_dir, 'probability.pickle')

#creating folders
if not isdir(join(main_dir,'slides')):
    raise Exception('Given path to folder does not exist')

slides_dir = join(main_dir, 'slides')

if not all([x.endswith('.svs') for x in listdir(slides_dir)]):
    raise Exception('Slides folder contains non-svs files, please remove them and try again')

if not exists(pickle_file):
    raise Exception('Given path to model folder does not contain probabilities, please use probability_finder.py for collecting probabilities and then try again.')

patch_annotator =  dict()
with open(pickle_file, 'rb+') as prob_file:
    try:
        patch_annotator = pickle.load(prob_file)
    except:
        raise Exception('Corrupted probability.pickle, please use probability_finder.py for collecting probabilities and then try again.')

heatmap_dir = join(args.model_dir, 'heatmaps')

if not exists(heatmap_dir):
    makedirs(heatmap_dir)

#initialize parameters
patch_size = args.patch_size

def convert_to_rgb(value, minimum=0, maximum=1):
    minimum, maximum = float(minimum), float(maximum)    
    halfmax = (minimum + maximum) / 2
    if minimum <= value <= halfmax:
        r = 0
        g = int( 255./(halfmax - minimum) * (value - minimum))
        b = int( 255. + -255./(halfmax - minimum)  * (value - minimum))
        return (r,g,b)    
    elif halfmax < value <= maximum:
        r = int( 255./(maximum - halfmax) * (value - halfmax))
        g = int( 255. + -255./(maximum - halfmax)  * (value - halfmax))
        b = 0
        return (r,g,b)

def generate_heatmap(slide):
    # extract patches    
    # whiteness limit
    prob_tuples = patch_annotator[slide]
    probability = dict()
    for prob_tuple in prob_tuples:
        probability[(prob_tuple[0], prob_tuple[1])] = prob_tuple[2]
    
    file = slide + '.svs'

    whiteness_limit = (patch_size ** 2) / 2 

    # open svs slide image
    try:
        osr = openslide.OpenSlide(join(slides_dir, file))
    except:
        print(file)
        return 0

    count = 0

    x_limit = osr.dimensions[0]-osr.dimensions[0]%patch_size
    y_limit = osr.dimensions[1]-osr.dimensions[1]%patch_size
    x_patches = x_limit // patch_size
    y_patches = y_limit // patch_size

    WSI = Image.new('RGBA', (x_patches * 32,  y_patches * 32), color=0)
    
    # slide across slide taking patches
    for x in range(0, x_limit, patch_size):
        for y in range(0, y_limit, patch_size):

            foreground = osr.read_region(location=(x, y), level=0, size=(patch_size, patch_size))
            foreground.putalpha(128)
            
            prob = probability[(x,y)] if (x, y) in probability else 0

            background = Image.new('RGBA', size=(patch_size, patch_size), color=convert_to_rgb(prob)).convert('RGBA')
            background.putdata([ (255, 255, 255, b[3]) if f[0] > 210 and f[1] > 210 and f[2] > 210 else b for b, f in zip(background.getdata(), foreground.getdata())])
            background.paste(foreground, (0, 0), foreground)
            background.thumbnail((32,32))
            
            position = ((x//patch_size) * 32, (y//patch_size) * 32)
            WSI.paste(background, position , background)
            
            count += 1
    
    WSI.thumbnail((1024, 1024))
    WSI.convert('RGB').save(join(heatmap_dir, slide + '.jpg'))

count = 1
total = len(patch_annotator.keys())
for slide in patch_annotator.keys():
    generate_heatmap(slide)
    print('generating heatmap', count, '/', total, end='\r')
    sleep(0.03)
    count += 1
    
print("\n probability heatmap generation completed.")
