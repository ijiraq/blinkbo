"""
An object to hold the required information for a stack of images used for blinking.
"""
import argparse
import glob
import os
import re
from astropy.io import fits
import ds9
import math

__author__ = 'jjk'

DISPLAY_NAME = "blinkbo"


USAGE = """

The stack program displays all images matching the given pattern in a ds9 display and then starts blinking through them.

The stack of images is display in section of 128x128 pixel and the user progresses through sections of the image.

Below is a list of key-strokes that do stuff.   The ds9 display must be selected to to enable these keystrokes.

b - toggle blinking off and on.
a - Add point at cursor to found object list.
d - Delete mark(s) within 1 pixel of cursor from found object list.
n - go to next section of the image.
p - go to previous section of the image.
q - quit.
? - print this h
"""

class Stack(object):

    coo_extension = '.coo'

    def __init__(self, dir_name, pattern="*.fits"):
        """

        :param dir_name: directory containing the images to display in a stack.
        :param pattern: a pattern to match those images.
        """
        self.dir_name = dir_name
        self.pattern = pattern
        self._limits = None

    @property
    def file_names(self):
        return glob.glob(os.path.join(self.dir_name, self.pattern))

    @property
    def limits(self):
        if self._limits is None:
            hdulist = fits.open(self.file_names[0])
            xmax = hdulist[0].header['NAXIS1']
            ymax = hdulist[0].header['NAXIS2']
            self._limits = xmax, ymax
        return self._limits


class DisplayManager(object):


    reg_extension = 'coo'

    def __init__(self, name=DISPLAY_NAME):
        self.display = ds9.ds9(target=name)
        self.clear()
        self.__setup()
        self.filenames = {}
        self.sections = {}

    def __setup(self):
        self.display.set('scale zscale')
        self.display.set('cmap invert yes')
        self.display.set('blink interval 0.25')
        self.display.set('view info no')
        self.display.set('view magnifier no')
        self.display.set('view panner no')
        self.display.set('view buttons no')
        self.blink('on')

    @property
    def frame_number(self):
        return int(self.display.get('frame frameno'))

    @property
    def region_filename(self):
        idx = self.frame_number
        return os.path.splitext(self.filenames[idx])[0]+'.'+DisplayManager.reg_extension

    def load_regions(self):
        if not os.access(self.region_filename, os.F_OK):
            return

        section = self.sections[self.frame_number]
        if section == "None":
            section = (1, 0, 1, 0)
        for line in open(self.region_filename, 'r'):
            x, y = line.split()
            x = float(x) - section[0] + 1.0
            y = float(y) - section[2] + 1.0
            self.mark(x,y)

    @property
    def regions(self):
        regions = []
        for line in self.display.get('regions').split('\n'):
            line = line.strip()
            if 'circle' in line:
                region = re.match('circle\((.*),(.*),(.*)\).*', line)
                regions.append((float(region.groups()[0]), float(region.groups()[1])))
        return regions

    def save_regions(self):
        f = open(self.region_filename, 'w')
        section = self.sections[self.frame_number]
        if section == "None":
            section = (1,0,1,0)
        for region in self.regions:
            x = region[0] + section[0] - 1
            y = region[1] + section[1] - 1
            f.write("{:12.2f} {:12.2f}\n".format(x, y))
        f.close()

    def delete_region(self, x, y):
        lines = open(self.region_filename, 'r').readlines()
        os.unlink(self.region_filename)
        self.display.set("region delete all")
        for line in lines:
            v = line.split()
            rx = float(v[0])
            ry = float(v[1])
            if math.sqrt((rx-x)**2 + (ry-y)**2) < 1:
                continue
            self.mark(rx, ry)
        self.save_regions()

    def next_frame(self):
        self.display.set('frame next')

    def load_image(self, image_name, section=None, frameno=None):
        if frameno is None:
            self.display.set('frame new')
        self.display.set('cmap invert yes')
        if section is None:
            cutout = "[*,*]"
        else:
            cutout = ("[{}:{},{}:{}]".format(section[0], section[1], section[2], section[3]))

        self.display.set('file {}{}'.format(image_name, cutout))
        self.filenames[self.frame_number] = image_name
        self.sections[self.frame_number] = section
        self.display.set('zoom to fit')
        self.label(section[1] - 10, (section[2]+section[3])/2.0, image_name+cutout)
        self.load_regions()

    def label(self, x, y, text):
        self.display.set('regions',
                         "image; text %f %f # text={%s}" % ( x, y, text))

    def load_images(self, stack, section=None):
        """
        Load the given list of file_names.  Turn off blinking first if its on... turn back on after loading.
        """

        blinking = self.blinking
        if blinking:
            self.blink('no')

        for file_name in stack.file_names:
            self.load_image(file_name, section)

        if blinking:
            self.blink('yes')

    def imexam(self):
        command = 'imexam key coordinate image'
        f = lambda: None
        result = None
        while result is None:
            try:
                result = self.display.get(command).split()
            except ValueError:
                result = None
                pass
        f.key = result[0]
        f.x = float(result[1])
        f.y = float(result[2])
        return f

    @property
    def blinking(self):
        return self.display.get('blink') == 'yes'

    def blink(self, setting=None):
        self.display.set('blink {}'.format(setting is not None and setting or self.blinking and 'no' or 'yes'))

    def clear(self):
        self.display.set("frame delete all")

    def mark(self, x, y, radius=10, colour='red'):
        self.display.set('regions', 'image; circle({},{},{}) # color={}'.format(x, y, radius, colour))


if __name__ == '__main__':

    parser = argparse.ArgumentParser(usage=USAGE)
    parser.add_argument('--pattern', help="File pattern used to build display stack", default="s*.fits")
    args = parser.parse_args()
    width = 128
    stack = Stack('.', pattern=args.pattern)
    dxs = range(1, stack.limits[0]+1, width)
    dys = range(1, stack.limits[1]+1, width)

    sections = []
    for x1 in dxs:
        for y1 in dys:
            sections.append((x1, x1+width, y1, y1+width))

    coo = '.coo'

    d = DisplayManager()

    idx = 0
    d.clear()
    d.load_images(stack, section=sections[idx])

    while True:
        response = d.imexam()

        if response.key == 'n':
            ## set the idx value to load the next section in the series.
            idx = min(idx+1, len(sections)-1)
            d.clear()
            d.load_images(stack, section=sections[idx])
        if response.key == 'p':
            ## set the idx value to load the previous section in the series.
            idx = max(idx-1, 0)
            d.clear()
            d.load_images(stack, section=sections[idx])
        if response.key == 'b':
            ## toggle blinking the images.
            d.blink()
        if response.key == 'a':
            if d.blinking:
                print "Toggle off blink (b) before marking."
                continue

            ## add a marker to the frames at the current location.
            d.mark(response.x, response.y)
            x = sections[idx][0] + response.x - 1
            y = sections[idx][2] + response.y - 1
            d.save_regions()
        if response.key == 'd':
            if d.blinking:
                print "Toggle off blink (b) before deleting a mark."
                continue
            x = sections[idx][0] + response.x - 1
            y = sections[idx][2] + response.y - 1
            d.delete_region(x, y)
            d.load_image(stack.file_names[d.frame_number - 1], section=sections[idx])
        if response.key == 'question':
            parser.print_help()

        if response.key == 'q':
            d.blink('no')
            break
