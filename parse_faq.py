import numpy as np
from bs4 import BeautifulSoup
import cssutils as csu
from copy import copy
from argparse import ArgumentParser
import re
import urllib
import os, sys

####
# parse google doc of faq (html download) and reformat
# for OJS site with anchor links (instead of collapsible headings)
#
# TODO:
    # cleanup, tests
    # figure out line breaks for answers if we want multiple paragraphs
    # possibly update scope link/any other links to policies or guidelines?
#
####

def strip_comments(soup,cmt_class):
    """
    decompose divs and <a>s from comments
    """
    for div in soup.find_all('div',class_=cmt_class):
        div.decompose()
    for a in soup.find_all(id=re.compile('^cmnt')):
        a.decompose()
    return soup

def find_comment_class(soup):
    """
    figure out what the css tag is for divs around comments so we can strip all of them out
    """
    divs = soup.find_all('div')
    for d in divs:
        aas = d.find_all(id=re.compile('^cmnt'))
        if len(aas) > 0:
            return d.attrs['class']  # assume all comments are the same class (seems safe)

def clean_soup(soup,h6=True,notext=True,aempty=True,sup=True):
    """
    clean up various kinds of empty tags that tend to show up in these files
    h6 and sup are mainly in the guidelines; notext and aempty are in both, probably?
    """
    if h6:
        for h in soup.find_all('h6'):
            h.unwrap()

    ingredients = soup.body.find_all(recursive=False)
    if notext:
        for ing in ingredients:
            if ing.text == None or ing.text == '':
                ing.decompose()
    if aempty:
        for a in soup.find_all('a'):
            if a.string == None:
                a.decompose()
    if sup:
        for s in soup.find_all('sup'):
            if s.string == None:
                s.decompose()
    return soup

def clean_spans(soup,translate={}):
    """
    get rid of empty span elements (mostly in guidelines) and translate any classes that 
    we can figure out (also mostly in guidelines)
    """
    for sp in soup.find_all('span'):
        for k in translate.keys():
            if 'class' in sp.attrs and k in sp.attrs['class']:
                for a in translate[k]:
                    sp.wrap(copy(a))
        sp.unwrap()
    return soup


def get_Q_A(ingredients):
    """
    from a soup, extract indices of <strong>Q</strong> and <strong>A</strong> lines
    these will be used to set up accordions
    """
    Qind = []; Aind = []
    for i,ing in enumerate(ingredients):
        if bool(ing.strong):
            if ing.strong.text.startswith('Q'):
                Qind.append(i)
            if ing.strong.text.startswith('A'):
                Aind.append(i)
    return Qind,Aind

def class_translate(sheet,css_keys,match='.c'):
    """
    scan a stylesheet for (.c#) rules and pick out a particular set of css keys
    return dict of (.c#) keys and html tags that they should get, based on input css_keys dict
    """
    translate = {}
    for rule in sheet:  # loop all rules
        try:
            if rule.selectorText.startswith(match):  # find rules matching name criterion
                ruledict = {}
                for k in css_keys.keys():  # find style tags that match css_keys top level
                    if k in rule.style.keys():
                        ruledict[k] = rule.style[k]
                rulelist = []
                if ruledict != {}:
                    for k in ruledict.keys():  # check whether tag contents need to be translated
                        if ruledict[k] in css_keys[k].keys():
                            rulelist.append(css_keys[k][ruledict[k]])
                if len(rulelist) > 0:
                    # if tag needs translation, translate it
                    # NOTE we strip leading . from the rule name
                    translate[rule.selectorText.split('.')[-1]] = rulelist
        except AttributeError:
            pass  # no selectorText, probably the link at the top
    return translate

# here are some css tags that we want to translate, and how we want to translate them
# NOTE <u> is maybe not best practice? Also here I think it only applies to hyperlinks.
css_keys = {'font-weight':{'700':'strong'},\
            'font-style':{'italic':'em'},\
            'text-decoration':{'underline':'u'},\
            'background-color':{'#ff0':'mark'}}

def _has_href(tag):
    """
    function to pass to find_all() to get all hyperlinks
    """
    return tag.has_attr('href')

if __name__ == '__main__':

    # start by exporting google doc as html and extracting the html file from the zip archive
    # (we don't need any image files afaik)

    # filename  can be set by command line args
    # if not  present, we ask for the info via input()
    parser = ArgumentParser()
    parser.add_argument('--ifile','-f',metavar='ifile',type=str,help='path to input file')
    args = parser.parse_args()

    ifile = args.ifile
    if ifile == None:
        ifile = input('Enter path to input file: ') or 'Seismica_FAQ.html'
    assert os.path.isfile(ifile),'file does not exist'

    # set ofile names
    ofile = 'out_faq.html'

    # then:
    f = open(ifile,'r') # open html file
    text = f.readline()  # google docs outputs html as one single line, weirdly
    f.close()
    soup = BeautifulSoup(text,'html.parser')  # parse to a soup
    header = soup.head.extract()
    if bool(soup.img): soup.img.decompose()  # get rid of the header image (seismica logo)
        # (only for guidelines, but doesn't hurt ed pol b/c there are no images in it)

    # deal with css style in header, to some extent
    style = csu.parseString(header.style.text)  # parses to CSSStyleSheet object
    # we will only look at .c# styles, and find italics, bold, and underline
    #   [info on what is looked for/translated is in css_keys before __main__]
    # we're skipping all the hyper-specific list element formatting at the moment
    translate_tags = class_translate(style,css_keys)
    translate = {}  # need to actually make soup tags to wrap things in; do this outside of function
    for k in translate_tags.keys():
        translate[k] = []
        for a in translate_tags[k]:
            translate[k].append(soup.new_tag(a))

    # figure out what the comment div class name is, strip out comments
    cmt_class = find_comment_class(soup)
    soup = strip_comments(soup,cmt_class=cmt_class)

    # clean up span formatting, translate to html tags since we can't use css header
    soup = clean_spans(soup,translate=translate)

    # clean out empty tags etc
    soup = clean_soup(soup)  # not all apply to ed pol, but that's actually fine

    # make a copy of the soup and empty it so we can add things back in
    bowl = copy(soup)
    bowl.body.clear()
    del bowl.body['class']  # for neatness

    # set up generic tags for each anchor
    hdiv = bowl.new_tag('div'); hdiv.attrs['class'] = 'heading-wrapper'
    hashspan = bowl.new_tag('span'); hashspan.attrs['aria-hidden'] = 'true'; hashspan.string = '#'
    hashspan.attrs['class'] = 'anchor-icon'
    Qspan = bowl.new_tag('span'); Qspan.string = 'title here'; # Qspan.attrs['class'] = 'hidden'
    alink = bowl.new_tag('a'); alink.attrs['href'] = '#title'; alink.attrs['class'] = 'anchor-link'
    h2 = bowl.new_tag('h2'); h2.attrs['id'] = 'title'; h2.string = 'title'

    # set up ul and li for table of contents
    contents = bowl.new_tag('ul')
    li = bowl.new_tag('li')
    lia = bowl.new_tag('a')
    
    # go through body of soup element-wise, and deal with each in turn
    ingredients = soup.body.find_all(recursive=False)  # reset list

    # run through ingredients and map out where the headers and such are for overall structure
    Qind,Aind = get_Q_A(ingredients)
    Qind.append(len(ingredients))

    # start filling the bowl
    for i in range(len(Qind)-1):  # looping questions

        ing = ingredients[Qind[i]]  # get the question element

        qtag = ing.string.lstrip('Q.').lstrip().rstrip('?').replace(' ','-') # set up identifier text

        # set up styling div
        idiv = copy(hdiv)
        bowl.body.append(idiv)

        # set up header with Q info, add to bowl
        ih2 = copy(h2); ih2.attrs['id'] = qtag
        ih2.string = ing.string.lstrip('Q.').lstrip()
        ia = copy(alink); ia.attrs['href'] = '#%s' % qtag
        is1 = copy(hashspan);
        is2 = copy(Qspan); is2.string = ih2.string;

        ia.extend([is1,is2])
        idiv.extend([ih2,ia])

        is2.attrs['class'] = 'hidden'

        # add li to contents
        ili = copy(li)
        ilia = copy(lia); ilia.attrs['href'] = '#%s' % qtag; 
        ilia.string = ing.string.lstrip('Q.').lstrip()
        ili.append(ilia)
        contents.extend([ili])

        # go through the A markers, and between each, preserve whatever's there

        for j in range(Qind[i]+1,Qind[i+1]):
            if ingredients[j].strong.text.startswith('A'):
                _ = ingredients[j].strong.extract()
            bowl.body.append(ingredients[j])

    # unwrap hyperlinks that google has wrapped with extra stuff
    links = bowl.find_all(_has_href)
    for link in links:
        if link.attrs['href'].startswith('#') or link.attrs['href'].startswith('mailto'):
            continue
        link.attrs['href'] = urllib.parse.unquote(link.attrs['href'].split('?q=')[1].split('&')[0])

    # add the table of contents to the top
    chead = bowl.new_tag('h2'); chead.string = 'Contents:'
    bowl.body.insert(0,contents)
    bowl.body.insert(0,chead)

    # write
    bowl.smooth()
    f = open(ofile,'w')
    #f.write(bowl.prettify())   # for reading html and figuring out what is wrong
    f.write(str(bowl))          # for actual writing with proper spaces
    f.close()

