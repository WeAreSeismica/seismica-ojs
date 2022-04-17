import numpy as np
import re
from bs4 import BeautifulSoup
from copy import copy
import os, sys

####
# parse google doc of guidelines or editorial policies (html download) and reformat
# for OJS site with (nested?) dropdowns
#
# TODO:
    # find consecutive <b> tags and combine? Or don't even bother because they are hella weird?
    # figure out parsing for nested lists (start != 1)
    # get rid of superflous/possibly actually bad class tags
    # nested accordions? Do we want that or need that?
    # URLs - do we care that google prefixes them?
#
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

# start by exporting google doc as html and extracting the html file from the zip archive
# (we don't need the header image file)

f = open('TaskForce2_Guidelines.html','r') # open html file
text = f.readline()  # google docs outputs html as one single line
f.close()
soup = BeautifulSoup(text,'html.parser')  # parse to a soup
soup.head.decompose()  # get rid of the long css/google doc styling string that we will not use
soup.img.decompose()  # get rid of the header image (seismica logo)


# google docs translations for span classes
translate = {'c23':soup.new_tag('b')}

# strip out any comments from the doc
for div in soup.find_all('div',class_='c11'):
    div.decompose()
for a in soup.find_all(id=re.compile('^cmnt')):
    a.decompose()

# clean up span formatting, not needed for website
for sp in soup.find_all('span'):
    for k in translate.keys():
        if 'class' in sp.attrs and k in sp.attrs['class']:
            sp.wrap(copy(translate[k]))
    sp.unwrap()

# also clean up some weird h6 stuff that shows up in the reviewer recommendations table
for h in soup.find_all('h6'):
    h.unwrap()

# strip out elements that don't have any text in them
ingredients = soup.body.find_all(recursive=False)
for ing in ingredients:
    if ing.text == None or ing.text == '':
        ing.decompose()
for a in soup.find_all('a'):
    if a.string == None:
        a.decompose()
for s in soup.find_all('sup'):
    if s.string == None:
        s.decompose()


# make a copy of the soup and empty it so we can add things back in
bowl = copy(soup)
bowl.body.clear()
del bowl.body['class']

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
hdr1 = []; hdr2 = [];
for i,ing in enumerate(ingredients):
    if bool(ing.h1):
        hdr1.append(i)
    elif bool(ing.h2):
        hdr2.append(i)
hdr1.append(len(ingredients)+1)  # dummy entry for EOL
hdr1 = np.array(hdr1); hdr2 = np.array(hdr2)

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
            #print(hdr1[i],hdr2_use[j],k)
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

# write
bowl.smooth()
f = open('output.html','w')
f.write(bowl.prettify())
f.close()

