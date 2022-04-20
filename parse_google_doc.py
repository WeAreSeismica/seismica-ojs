import numpy as np
import re
from bs4 import BeautifulSoup
from copy import copy
from argparse import ArgumentParser
import os, sys

####
# parse google doc of guidelines or editorial policies (html download) and reformat
# for OJS site with (nested?) dropdowns
#
# TODO:
    # find consecutive <b> tags and combine? Or don't even bother because they are hella weird?
    # figure out parsing for nested lists (start != 1) - scan backwards, unless heading
    # triple nesting (References in author guidelines, in particular)
    # get rid of superflous/possibly actually bad class tags
    # nested accordions? at least for one spot in ed pol?
    # URLs - do we care that google prefixes them?
    # put three guidelines sections into three files? or just don't
    # MORE COMMENTS for bits that are likely to break in the future if formatting changes
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

def strip_comments(soup,cmt_class='c11'):
    """
    decompose divs and <a>s from comments
    c11 for guidelines, c13 for editorial policies; no idea why they are different
    """
    for div in soup.find_all('div',class_=cmt_class):
        div.decompose()
    for a in soup.find_all(id=re.compile('^cmnt')):
        a.decompose()
    return soup

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
                sp.wrap(copy(translate[k]))
        sp.unwrap()
    return soup


def get_h1_h2(ingredients):
    """
    from a soup, extract indices of elements that contain h1 or h2 tags
    hdr1 has one extra element added for fenceposting
    """
    hdr1 = []; hdr2 = []
    for i,ing in enumerate(ingredients):
        if bool(ing.h1):
            hdr1.append(i)
        elif bool(ing.h2):
            hdr2.append(i)
    hdr1.append(len(ingredients)+1)  # dummy entry for EOL
    hdr1 = np.array(hdr1); hdr2 = np.array(hdr2)
    return hdr1, hdr2

if __name__ == '__main__':

    # start by exporting google doc as html and extracting the html file from the zip archive
    # (we don't need any image files afaik)

    # filename and type (guidelines or not, ie editorial policies) can be set by command line args
    # if those aren't present, we ask for the info via input()
    parser = ArgumentParser()
    parser.add_argument('--ifile','-f',metavar='ifile',type=str,help='path to input file')
    parser.add_argument('--isguide','-g',metavar='isguide',type=int,\
            help='is this guidelines or not? True[1]/False[0]')
    args = parser.parse_args()

    if args.ifile == None:
        ifile = input('Enter path to input file: ') or 'TaskForce2_Guidelines.html'
    else:
        ifile = args.ifile
    assert os.path.isfile(ifile),'file does not exist'

    if args.isguide == None:
        isguide = bool(input('Is this the guidelines file? [True/1]/False/0: ') or 1)
    else:
        isguide = bool(args.isguide)

    # then:
    f = open(ifile,'r') # open html file
    text = f.readline()  # google docs outputs html as one single line, weirdly
    f.close()
    soup = BeautifulSoup(text,'html.parser')  # parse to a soup
    soup.head.decompose()  # get rid of the long css/google doc styling string that we will not use
    soup.img.decompose()  # get rid of the header image (seismica logo)

    # set some things that differ between guidelines and editorial policies
    if isguide:
        cmt_class = 'c11'
        translate = {'c23':soup.new_tag('b')}  # google docs translations for span classes
        ofile = 'out_guides.html'
    else:
        cmt_class = 'c13'
        translate = {}
        ofile = 'out_edpol.html'

    # strip out any comments from the doc
    soup = strip_comments(soup,cmt_class=cmt_class)

    # clean up span formatting, not needed for website (mostly pertains to guidelines)
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
    hdr1, hdr2 = get_h1_h2(ingredients)

    # SPLIT HERE for ed pol vs guidelines in main loop

    if isguide:
        for i in range(len(hdr1)-1):  # looping level 1 (Authors, Reviewers, Editors)
            # put in h1 header for marking
            h1 = ingredients[hdr1[i]]  # get the h1 element
            new = bowl.new_tag('h1'); new.string = h1.text   # make a new tag for it
            bowl.body.append(new)

            # start building the accordion
            acc_id = 'acc_%i' % i  # id
            accord = bowl.new_tag('div'); accord.attrs = {'id':acc_id,'class':'accordion'}
            bowl.body.append(accord)  # we'll insert elements as they are made

            # go through the h2 markers, and between each, preserve whatever's there
            ic = 0  # counter for collapsible headings
            hdr2_use = hdr2[np.logical_and(hdr2>hdr1[i],hdr2<hdr1[i+1])]
            hdr2_use = np.append(hdr2_use,hdr1[i+1])  # bookends again
            for j in range(len(hdr2_use)-1):
                icard = copy(card)
                accord.append(icard)
                ing = ingredients[hdr2_use[j]]
                ispan = copy(span); ispan.string = ing.text.strip()
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

                for k in range(hdr2_use[j]+1,hdr2_use[j+1]):
                    try:
                        ing = ingredients[k]
                    except IndexError:  # reached end of list, hopefully
                        break
                    # if we don't break things, move on to check this element
                    if ing.name == 'table': # this should be the reviewer recommendations table
                        ing.attrs['class'] = 'table'
                        if not bool(ing.thead):  # no header line, need to make the first row a header
                            first_row = ing.tr.extract()
                            thead = bowl.new_tag('thead')
                            ing.insert(0,thead)
                            thead.append(first_row)
                            for td in first_row.find_all('td'): 
                                td.wrap(bowl.new_tag('th')) 
                                td.unwrap() 
                        idivtext.append(ing)

                    elif ing.name == 'ul':  # put this back in the hierarchy with the previous ol
                        prev = ingredients[k-1]  # should be ol
                        if prev.name == 'ol':
                            prev = idivtext.find_all('ol')[-1]
                            ul = ing.extract()
                            prev.append(ul)
                        else:
                            idivtext.append(ing)

                    else:
                        idivtext.append(ing)

    else:
        # start building the accordion for everything
        acc_id = 'acc_0' # there's only one accordion for all edpol (the zeroth one)
        accord = bowl.new_tag('div'); accord.attrs = {'id':acc_id,'class':'accordion'}
        bowl.body.append(accord)  # we'll insert elements as they are made
        for ic in range(len(hdr1)-1):  # looping level 1 (section headings)
            h1 = ingredients[hdr1[ic]].h1
            icard = copy(card)
            accord.append(icard)
            ing = ingredients[hdr1[ic]]
            ispan = copy(span); ispan.string = ing.text.strip()
            icard.insert(0,ispan)
            ibutton = copy(button)
            ibutton.attrs['data-target'] = '#collapse%02d' % ic
            ibutton.attrs['aria-controls'] = 'collapse%02d' % ic
            ispan.wrap(ibutton)
            #ih1 = copy(h1); ibutton.wrap(ih1)
            idivhead = copy(divhead); idivhead.attrs['id'] = 'heading%02d' % ic
            #ih1.wrap(idivhead)
            ibutton.wrap(idivhead)

            idivcoll = copy(divcoll)
            idivcoll.attrs['id'] = 'collapse%02d' % ic
            idivcoll.attrs['aria-labelledby'] = 'heading%02d' % ic
            idivcoll.attrs['data-parent'] = '#%s' % acc_id
            icard.insert(1,idivcoll)

            idivtext = copy(divtext)
            idivcoll.insert(0,idivtext)

            for k in range(hdr1[ic]+1,hdr1[ic+1]):
                #print(hdr1[i],hdr2_use[j],k)
                try:
                    ing = ingredients[k]
                except IndexError:  # reached end of list, hopefully
                    break
                # if we don't break things, move on to check this element
                if ing.name == 'table':
                    ing.attrs['class'] = 'table'
                    if not bool(ing.thead):  # no header line, need to make the first row a header
                        first_row = ing.tr.extract()
                        thead = bowl.new_tag('thead')
                        ing.insert(0,thead)
                        thead.append(first_row)
                        for td in first_row.find_all('td'): 
                            td.wrap(bowl.new_tag('th')) 
                            td.unwrap() 
                    idivtext.append(ing)

                elif ing.name == 'ul':  # put in the hierarchy with the previous ol, if there is one
                    prev = ingredients[k-1]
                    if prev.name == 'ol':   # check if previous actually is ol (edpol has fewer nests)
                        prev = idivtext.find_all('ol')[-1]
                        ul = ing.extract()
                        prev.append(ul)
                    else:
                        idivtext.append(ing)

                else:
                    idivtext.append(ing)

    # write
    bowl.smooth()
    f = open(ofile,'w')
    f.write(bowl.prettify())
    f.close()

