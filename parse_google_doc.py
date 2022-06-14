import numpy as np
import pandas as pd
from bs4 import BeautifulSoup
import cssutils as csu
from copy import copy
from argparse import ArgumentParser
import re
import urllib
import os, sys

####
# parse google doc of guidelines AND editorial policies (html download) and reformat
# for OJS site with (nested?) dropdowns
#
# TODO:
    # catch for any hdr2 sections that *start* with <ol> or <ul> (ln 344, 'prev' etc)
    # re-combine oddly segmented nested lists? Might be more trouble than it's worth
    # nested accordions? at least for one spot in policies for data availability/types
        # and/or other things that are in paragraph-sections (could also reformat as ol post-google)
# TODO for google doc formatting to make this work:
    # links between sections and between different documents: numbers mean nothing
    # weird italicized *Seismica*'s things in ed pol
    # get rid of as many numbered lists as possible
    # update links (esp cross-document) to the right things, un-highlight
    # can we fix the excess spaces around formatted text without doing stupid amounts of work?

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


def get_h1_h2(ingredients):
    """
    from a soup, extract indices of elements that contain h1 or h2 tags
    hdr1 has one extra element added for fenceposting
    """
    hdr1 = []; hdr2 = []
    hdr1_text = []; hdr2_text = []
    for i,ing in enumerate(ingredients):
        if bool(ing.h1) or ing.name == 'h1':
            hdr1.append(i)
            gettext = ing.text.lower()
            gettext = re.sub(r'[^\w\s]','',gettext)  # strip out punctuation
            hdr1_text.append(gettext.replace(' ','-'))  # (messes with acc)
        elif bool(ing.h2):
            hdr2.append(i)
            gettext = ing.text.lower()
            gettext = re.sub(r'[^\w\s]','',gettext)
            hdr2_text.append(gettext.replace(' ','-'))
    hdr1.append(len(ingredients)+1)  # dummy entry for EOL
    hdr1 = np.array(hdr1); hdr2 = np.array(hdr2)
    return hdr1, hdr2, hdr1_text, hdr2_text

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

def _ol_info(idivtext):
    """
    get start numbers and #items in each ol in a chunk of stuff
    """
    ols = idivtext.find_all('ol',recursive=False)
    if len(ols) > 1:
        lis = np.zeros(len(ols),dtype=int); sts = np.zeros(len(ols),dtype=int)
        for io,ol in enumerate(ols):
            # count li elements at level 1
            lis[io] = len(ol.find_all('li',recursive=False))
            # get start #s
            sts[io] = int(ol.attrs['start'])
    return ols, sts, lis

def check_whose(idivtext):
    """
    test whether any bits of <ol> set are un-nested
    """
    ols = idivtext.find_all('ol',recursive=False)
    # check if we need to recursively nest any ols
    if len(ols) > 1:
        ol_list,sts,lis = _ol_info(idivtext)
        # see if sts and li are consistent with each other
        whose = np.cumsum(lis)[:-1] + 1 == sts[1:] 
        return np.all(whose)
    else:
        return True  # only one <ol>, everything is fine (or had better be)


def nest_in_between(idivtext):
    """
    nest extra bits (<p> etc) that fell between chunks of <ol>
    """
    ols = idivtext.find_all('ol',recursive=False)
    # check if we need to recursively nest any ols
    if len(ols) > 1:
        ol_list,sts,lis = _ol_info(idivtext)
        # see if sts and li are consistent with each other
        whose = np.cumsum(lis)[:-1] + 1 == sts[1:]
        for io in range(len(ol_list)-1):
            if ol_list[io].next_sibling.name != 'ol':  # something to append
                for g in ol_list[io].next_siblings:
                    if g == ol_list[io+1]:
                        break
                    else:
                        toadd = g.extract()
                        ol_list[io].append(toadd)

    return idivtext

def nest_lis(idivtext):
    """
    put <p> and similar elements that fall in <ol> but not <li> in <li>
    doesn't actually work at the moment (31 May 2022)
    or maybe sort of works but would need to be run iteratively or something?
    basically google docs does not understand lists with multiple paragraphs per <li>
    """
    ols = idivtext.find_all('ol',recursive=False)

    for ol in ols:
        lis = ol.find_all('li',recursive=False)
        ing = ol.find_all(recursive=False)
        if len(lis) != len(ing):  # there are elements that are not in list items
            if len(lis) > 1:
                for il in range(len(lis)-1):
                    if lis[il].next_sibling.name != 'li':
                        for g in lis[il].next_siblings:
                            if g == lis[il+1]:
                                break
                            else:
                                toadd = g.extract()
                                lis[il].append(toadd)
            else:
                if lis[0].next_sibling.name != 'li':
                    for g in lis[0].next_siblings:
                        toadd = g.extract()
                        lis[0].append(toadd)
    return idivtext

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

    # filename and type (guidelines or not, ie editorial policies) can be set by command line args
    # if those aren't present, we ask for the info via input()
    parser = ArgumentParser()
    parser.add_argument('--ifile','-f',metavar='ifile',type=str,help='path to input file')
    args = parser.parse_args()

    ifile = args.ifile
    if ifile == None:
        ifile = input('Enter path to input file: ') or 'combined_doc.html'
    assert os.path.isfile(ifile),'file does not exist'

    # set ofile names
    ofile = 'out_allthings.html'

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
    divtext = bowl.new_tag('div')



    # go through body of soup element-wise, and deal with each in turn
    ingredients = soup.body.find_all(recursive=False)  # reset list
    # run through ingredients and map out where the headers and such are for overall structure
    hdr1, hdr2, h1text, h2text = get_h1_h2(ingredients)

    everything = {}  # dict for holding content so we can transfer duplicates
    # start adding things to the bowl
    for i in range(len(hdr1)-1):  # looping level 1 (Authors, Reviewers, Editors)
        # put in h1 header for marking
        h1 = ingredients[hdr1[i]]  # get the h1 element
        new = bowl.new_tag('h1'); new.string = h1.text   # make a new tag for it
        bowl.body.append(new)  # for large-scale section divisions

        # set up ul and li for table of contents
        contents = bowl.new_tag('ul')
        li = bowl.new_tag('li')
        lia = bowl.new_tag('a')
        bowl.body.append(contents)  # add the contents for this section after h1

        # go through the h2 markers, and between each, preserve whatever's there
        ic = 0  # counter for collapsible headings
        hdr2_use = hdr2[np.logical_and(hdr2>hdr1[i],hdr2<hdr1[i+1])]
        hdr2_use = np.append(hdr2_use,hdr1[i+1])  # bookends again
        h2t_use = np.array(h2text)[np.logical_and(hdr2>hdr1[i],hdr2<hdr1[i+1])]
        h2t_use = np.append(h2t_use,'x')  # bookends again
        for j in range(len(hdr2_use)-1):
            
            ing = ingredients[hdr2_use[j]]

            itag = h2t_use[j]  # already replaced ' ' with '-'

            # set up styling div
            idiv = copy(hdiv)
            bowl.body.append(idiv)

            # set up h2, add to bowl
            ih2 = copy(h2); ih2.attrs['id'] = itag
            ih2.string = ing.text.strip()
            ia = copy(alink); ia.attrs['href'] = '#%s' % itag
            is1 = copy(hashspan);
            is2 = copy(Qspan); is2.string = ih2.string;

            ia.extend([is1,is2])
            idiv.extend([ih2,ia])

            is2.attrs['class'] = 'hidden'

            # add li to contents
            ili = copy(li)
            ilia = copy(lia); ilia.attrs['href'] = '#%s' % itag; 
            ilia.string = ing.text.strip()
            ili.append(ilia)
            contents.extend([ili])

            # check if this content already exists in a previous accordion
            if len(everything) > 0 and h2t_use[j] in everything.keys():
                idivtext = copy(everything[h2t_use[j]])
            else:
                idivtext = copy(divtext)

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

                # check <ol>s within this card; if the first one has start != 1, reset it
                # (this happens at one particular point in the reviewer guidelines at the moment)
                ols = idivtext.find_all('ol')
                if len(ols) > 0 and ols[0].attrs['start'] != 1:
                    ols[0].attrs['start'] = '1'

                # check if we need to recursively nest any ols
                if check_whose(idivtext):
                    idivtext = nest_in_between(idivtext)
                else:
                    # there's a mis-nested thing here; deal with it
                    iq = False
                    ol_list,sts,lis = _ol_info(idivtext)
                    whose = np.cumsum(lis)[:-1] + 1 == sts[1:]
                    while not iq:
                        olstart = ol_list[np.where(whose == False)[0][0]]  # this should not work??
                        iadd = True
                        while iadd:
                            toadd = olstart.next_sibling.extract()
                            if toadd.name == 'ol':
                                iadd = False
                            olstart.append(toadd)
                        ol_list,sts,lis = _ol_info(idivtext)
                        whose = np.cumsum(lis)[:-1] + 1 == sts[1:]
                        if np.all(whose):
                            iq = True

                # nest extra bits (<p> etc) one more time now that numbers are matched
                idivtext = nest_in_between(idivtext)
                #idivtext = nest_lis(idivtext)  # this does not work, so I decided not to need it

                everything[h2t_use[j]] = idivtext  # save in case this is duplicated

            bowl.body.append(idivtext)


    # unwrap hyperlinks that google has wrapped with extra stuff
    links = bowl.find_all(_has_href)
    for link in links:
        if link.attrs['href'].startswith('#') or link.attrs['href'].startswith('mailto'):
            continue
        link.attrs['href'] = urllib.parse.unquote(link.attrs['href'].split('?q=')[1].split('&')[0])

    # write
    bowl.smooth()
    f = open(ofile,'w')
    #f.write(bowl.prettify())   # for reading html
    f.write(str(bowl))          # for actual display with proper spaces
    f.close()

