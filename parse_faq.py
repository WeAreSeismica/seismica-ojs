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
# for OJS site with dropdowns
#
# TODO:
    # cleanup, tests
    # figure out line breaks for buttons/cards? Is that possible or do all Qs need to be short?
#
# goal: something that looks like the following
#
#   <div id="accordionExample" class="accordion">
#   <div class="card">
#   <div id="headingOne" class="card-header">
#   <h2 class="mb-0"><button class="btn btn-lg btn-light btn-block collapsed" type="button" data-toggle="collapse" data-target="#collapseOne" aria-expanded="false" aria-controls="collapseOne"> <span class="pull-left"> heading here </span> </button></h2>
#   </div>
#   <div id="collapseOne" class="collapse" aria-labelledby="headingOne" data-parent="#accordionExample">
#   <div class="card-body">text here</div>
#   </div>
#   </div>
#   <div class="card">
#   <div id="headingTwo" class="card-header">
#   <h2 class="mb-0"><button class="btn btn-lg btn-light btn-block collapsed" type="button" data-toggle="collapse" data-target="#collapseTwo" aria-expanded="false" aria-controls="collapseTwo"> <span class="pull-left"> heading here </span> </button></h2>
#   </div>
#   <div id="collapseTwo" class="collapse" aria-labelledby="headingTwo" data-parent="#accordionExample">
#   <div class="card-body">text here</div>
#   </div>
#   </div>
#   </div>
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

    # set up generic accordion tags that can be modified later
    span = bowl.new_tag('span'); span.attrs['class'] = 'pull-left'; span.string = 'heading here'
    button = bowl.new_tag('button')
    button.attrs = {'class':"btn btn-lg btn-light btn-block collapsed",\
                    'type':'button',\
                    'data-toggle':'collapse',\
                    'data-target':'#collapse01',\
                    'aria-expanded':'false',\
                    'aria-controls':'collapse01'}
    h2 = bowl.new_tag('h2'); h2.attrs['class'] = 'mb-0'
    divhead = bowl.new_tag('div'); divhead.attrs = {'id':'heading01','class':'card-header'}
    divcoll = bowl.new_tag('div')
    divcoll.attrs = {'id':'collapse01','class':'collapse','aria-labelledby':'heading01',\
                    'data-parent':'#accid'}
    divtext = bowl.new_tag('div'); divtext.attrs['class'] = 'card-body';# divtext.string = 'text here'
    card = bowl.new_tag('div'); card.attrs['class'] = 'card'

    # go through body of soup element-wise, and deal with each in turn
    ingredients = soup.body.find_all(recursive=False)  # reset list

    # run through ingredients and map out where the headers and such are for overall structure
    Qind,Aind = get_Q_A(ingredients)
    Qind.append(len(ingredients))

    # start building the accordion
    acc_id = 'acc_0'
    accord = bowl.new_tag('div'); accord.attrs = {'id':acc_id,'class':'accordion'}
    bowl.body.append(accord)  # we'll insert elements as they are made
    ic = 0  # counter for collapsible headings
    for i in range(len(Qind)-1):  # looping questions
        # put in h1 header for marking
        ing = ingredients[Qind[i]]  # get the question element

        # go through the A markers, and between each, preserve whatever's there
        icard = copy(card)
        accord.append(icard)
        ispan = copy(span); ispan.string = ing.text.strip().split('Q. ')[1]
        icard.insert(0,ispan)
        ibutton = copy(button)
        ibutton.attrs['data-target'] = '#collapse%02d' % ic
        ibutton.attrs['aria-controls'] = 'collapse%02d' % ic
        ispan.wrap(ibutton)
        ih2 = copy(h2); ibutton.wrap(ih2)
        idivhead = copy(divhead); idivhead.attrs['id'] = 'heading%02d' % ic
        ih2.wrap(idivhead)

        idivcoll = copy(divcoll)
        idivcoll.attrs['id'] = 'collapse%02d' % ic
        idivcoll.attrs['aria-labelledby'] = 'heading%02d' % ic
        idivcoll.attrs['data-parent'] = '#%s' % acc_id
        icard.insert(1,idivcoll)

        idivtext = copy(divtext)
        idivcoll.insert(0,idivtext)
        ic += 1

        for j in range(Qind[i]+1,Qind[i+1]):
            if ingredients[j].strong.text.startswith('A'):
                _ = ingredients[j].strong.extract()
            idivtext.append(ingredients[j])

    # unwrap hyperlinks that google has wrapped with extra stuff
    links = bowl.find_all(_has_href)
    for link in links:
        if link.attrs['href'].startswith('#ftnt') or link.attrs['href'].startswith('mailto'):
            continue
        link.attrs['href'] = urllib.parse.unquote(link.attrs['href'].split('?q=')[1].split('&')[0])

    # write
    bowl.smooth()
    f = open(ofile,'w')
    #f.write(bowl.prettify())
    f.write(str(bowl))
    f.close()

