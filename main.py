# -*- coding: utf-8 -*-
from __future__ import division

import wsgiref.handlers
#from google.appengine.ext import webapp
import webapp2
from google.appengine.api import urlfetch
import os
import sys
import urllib
import urlparse
import re
import HTMLParser
import math
import urlparse
import posixpath

sys.path.insert(0, 'libs')

import chardet
from  BeautifulSoup import BeautifulSoup

from StringIO import StringIO

userKey=""
fontFile=u"simsun.ttc"
fontName=u'simsun'

####codes to solve the PDF's Chinese line-break problem below from http://slee.sinaapp.com/?p=76
import xhtml2pdf.reportlab_paragraph
from xhtml2pdf.reportlab_paragraph import LEADING_FACTOR

def wrap(self, availWidth, availHeight):
    # work out widths array for breaking
    self.width = availWidth
    style = self.style
    leftIndent = style.leftIndent
    first_line_width = availWidth - (leftIndent + style.firstLineIndent) - style.rightIndent
    later_widths = availWidth - leftIndent - style.rightIndent
    try:
        blPara = self.breakLinesCJK([first_line_width, later_widths])
    except:
        blPara = self.breakLines([first_line_width, later_widths])
    self.blPara = blPara
    autoLeading = getattr(self, 'autoLeading', getattr(style, 'autoLeading', ''))
    leading = style.leading
    if blPara.kind == 1 and autoLeading not in ('', 'off'):
        height = 0
        if autoLeading == 'max':
            for l in blPara.lines:
                height += max(l.ascent - l.descent, leading)
        elif autoLeading == 'min':
            for l in blPara.lines:
                height += l.ascent - l.descent
        else:
            raise ValueError('invalid autoLeading value %r' % autoLeading)
    else:
        if autoLeading == 'max':
            leading = max(leading, LEADING_FACTOR * style.fontSize)
        elif autoLeading == 'min':
            leading = LEADING_FACTOR * style.fontSize
        height = len(blPara.lines) * leading
    self.height = height
    return (self.width, self.height)

xhtml2pdf.reportlab_paragraph.Paragraph.wrap = wrap
#### end
import xhtml2pdf.pisa as pisa


class Readability:

    regexps = {
        'unlikelyCandidates': re.compile("combx|comment|community|disqus|extra|foot|header|menu|"
                                         "remark|rss|shoutbox|sidebar|sponsor|ad-break|agegate|"
                                         "pagination|pager|popup|tweet|twitter",re.I),
        'okMaybeItsACandidate': re.compile("and|artical|article|body|column|main|shadow", re.I),
        'positive': re.compile("artical|article|body|content|entry|hentry|main|page|pagination|post|text|"
                               "blog|story",re.I),
        'negative': re.compile("combx|comment|com|contact|foot|footer|footnote|masthead|media|"
                               "meta|outbrain|promo|related|scroll|shoutbox|sidebar|sponsor|"
                               "shopping|tags|tool|widget", re.I),
        'extraneous': re.compile("print|archive|comment|discuss|e[\-]?mail|share|reply|all|login|"
                                 "sign|single",re.I),
        'divToPElements': re.compile("<(a|blockquote|dl|div|img|ol|p|pre|table|ul)",re.I),
        'replaceBrs': re.compile("(<br[^>]*>[ \n\r\t]*){2,}",re.I),
        'replaceFonts': re.compile("<(/?)font[^>]*>",re.I),
        'trim': re.compile("^\s+|\s+$",re.I),
        'normalize': re.compile("\s{2,}",re.I),
        'killBreaks': re.compile("(<br\s*/?>(\s|&nbsp;?)*)+",re.I),
        'videos': re.compile("http://(www\.)?(youtube|vimeo)\.com",re.I),
        'skipFootnoteLink': re.compile("^\s*(\[?[a-z0-9]{1,2}\]?|^|edit|citation needed)\s*$",re.I),
        'nextLink': re.compile("(next|weiter|continue|>([^\|]|$)|»([^\|]|$))",re.I),
        'prevLink': re.compile("(prev|earl|old|new|<|«)",re.I)
    }

    def __init__(self, input, url):
        """
        url = "http://yanghao.org/blog/"
        htmlcode = urllib2.urlopen(url).read().decode('utf-8')

        readability = Readability(htmlcode, url)

        print readability.title
        print readability.content
        """
        self.candidates = {}

        self.input = input
        self.url = url
        self.input = self.regexps['replaceBrs'].sub("</p><p>",self.input)
        self.input = self.regexps['replaceFonts'].sub("<\g<1>span>",self.input)
#        stmp=self.input
        self.html = BeautifulSoup(self.input)

#        print self.html.originalEncoding
#        print self.html
        self.removeScript()
        self.removeStyle()
        self.removeLink()

        self.title = self.getArticleTitle()
        self.content = self.grabArticle()


    def removeScript(self):
        for elem in self.html.findAll("script"):
            elem.extract()

    def removeStyle(self):
        for elem in self.html.findAll("style"):
            elem.extract()

    def removeLink(self):
        for elem in self.html.findAll("link"):
            elem.extract()

    def grabArticle(self):
        content = ''

        for elem in self.html.findAll(True):
#            content=content+' '+elem.name
            unlikelyMatchString = elem.get('id','')+elem.get('class','')
            if self.regexps['unlikelyCandidates'].search(unlikelyMatchString) and \
                not self.regexps['okMaybeItsACandidate'].search(unlikelyMatchString) and \
                elem.name != 'body':
#                print elem
#                print '--------------------'
                elem.extract()
                continue
#                pass
            if elem.name == 'div':
                s = elem.renderContents(encoding=None)
                if not self.regexps['divToPElements'].search(s):
                    elem.name = 'p'

        for node in self.html.findAll('p'):
            parentNode = node.parent
            grandParentNode = parentNode.parent
            innerText = node.text

#            print '=================='
#            print node
#            print '------------------'
#            print parentNode

            if not parentNode or len(innerText) < 20:
                continue

            parentHash = hash(str(parentNode))
            grandParentHash = hash(str(grandParentNode))

            if parentHash not in self.candidates:
                self.candidates[parentHash] = self.initializeNode(parentNode)

            if grandParentNode and grandParentHash not in self.candidates:
                self.candidates[grandParentHash] = self.initializeNode(grandParentNode)

            contentScore = 1
            contentScore += innerText.count(',')
            contentScore += innerText.count(u'，')
            contentScore +=  min(math.floor(len(innerText) / 100), 3)

            self.candidates[parentHash]['score'] += contentScore

#            print '======================='
#            print self.candidates[parentHash]['score']
#            print self.candidates[parentHash]['node']
#            print '-----------------------'
#            print node

            if grandParentNode:
                self.candidates[grandParentHash]['score'] += contentScore / 2

        topCandidate = None

        for key in self.candidates:
#            print '======================='
#            print self.candidates[key]['score']
#            print self.candidates[key]['node']

            self.candidates[key]['score'] = self.candidates[key]['score'] * \
                                            (1 - self.getLinkDensity(self.candidates[key]['node']))

            if not topCandidate or self.candidates[key]['score'] > topCandidate['score']:
                topCandidate = self.candidates[key]


        if topCandidate:
            content = topCandidate['node']
#            print content
            content = self.cleanArticle(content)
        return content


    def cleanArticle(self, content):

        self.cleanStyle(content)
        self.clean(content, 'h1')
        self.clean(content, 'object')
        self.cleanConditionally(content, "form")

        if len(content.findAll('h2')) == 1:
            self.clean(content, 'h2')

        self.clean(content, 'iframe')

        self.cleanConditionally(content, "table")
        self.cleanConditionally(content, "ul")
        self.cleanConditionally(content, "div")

        self.fixImagesPath(content)

        content = content.renderContents(encoding=None)

        content = self.regexps['killBreaks'].sub("<br />", content)

        return content

    def clean(self,e ,tag):

        targetList = e.findAll(tag)
        isEmbed = 0
        if tag =='object' or tag == 'embed':
            isEmbed = 1

        for target in targetList:
            attributeValues = ""
            for attribute in target.attrs:
                attributeValues += target[attribute[0]]

            if isEmbed and self.regexps['videos'].search(attributeValues):
                continue

            if isEmbed and self.regexps['videos'].search(target.renderContents(encoding=None)):
                continue
            target.extract()

    def cleanStyle(self, e):

        for elem in e.findAll(True):
            del elem['class']
            del elem['id']
            del elem['style']

    def cleanConditionally(self, e, tag):
        tagsList = e.findAll(tag)

        for node in tagsList:
            weight = self.getClassWeight(node)
            hashNode = hash(str(node))
            if hashNode in self.candidates:
                contentScore = self.candidates[hashNode]['score']
            else:
                contentScore = 0

            if weight + contentScore < 0:
                node.extract()
            else:
                p = len(node.findAll("p"))
                img = len(node.findAll("img"))
                li = len(node.findAll("li"))-100
                input = len(node.findAll("input"))
                embedCount = 0
                embeds = node.findAll("embed")
                for embed in embeds:
                    if not self.regexps['videos'].search(embed['src']):
                        embedCount += 1
                linkDensity = self.getLinkDensity(node)
                contentLength = len(node.text)
                toRemove = False

                if img > p:
                    toRemove = True
                elif li > p and tag != "ul" and tag != "ol":
                    toRemove = True
                elif input > math.floor(p/3):
                    toRemove = True
                elif contentLength < 25 and (img==0 or img>2):
                    toRemove = True
                elif weight < 25 and linkDensity > 0.2:
                    toRemove = True
                elif weight >= 25 and linkDensity > 0.5:
                    toRemove = True
                elif (embedCount == 1 and contentLength < 35) or embedCount > 1:
                    toRemove = True

                if toRemove:
                    node.extract()


    def getArticleTitle(self):
        title = ''
        try:
            title = self.html.find('title').text
        except:
            pass

        return title


    def initializeNode(self, node):
        contentScore = 0

        if node.name == 'div':
            contentScore += 5;
        elif node.name == 'blockquote':
            contentScore += 3;
        elif node.name == 'form':
            contentScore -= 3;
        elif node.name == 'th':
            contentScore -= 5;

        contentScore += self.getClassWeight(node)

        return {'score':contentScore, 'node': node}

    def getClassWeight(self, node):
        weight = 0
        if 'class' in node:
            if self.regexps['negative'].search(node['class']):
                weight -= 25
            if self.regexps['positive'].search(node['class']):
                weight += 25

        if 'id' in node:
            if self.regexps['negative'].search(node['id']):
                weight -= 25
            if self.regexps['positive'].search(node['id']):
                weight += 25

        return weight

    def getLinkDensity(self, node):
        links = node.findAll('a')
        textLength = len(node.text)

        if textLength == 0:
            return 0
        linkLength = 0
        for link in links:
            linkLength += len(link.text)

        return linkLength / textLength

    def fixImagesPath(self, node):
        imgs = node.findAll('img')
        for img in imgs:
            src = img.get('src',None)
            if not src:
                img.extract()
                continue

            if 'http://' != src[:7] and 'https://' != src[:8]:
                newSrc = urlparse.urljoin(self.url, src)

                newSrcArr = urlparse.urlparse(newSrc)
                newPath = posixpath.normpath(newSrcArr[2])
                newSrc = urlparse.urlunparse((newSrcArr.scheme, newSrcArr.netloc, newPath,
                                              newSrcArr.params, newSrcArr.query, newSrcArr.fragment))
                img['src'] = newSrc

                

class MainPage(webapp2.RequestHandler):
    def get(self):
        self.response.headers['Content-Type'] = 'text/plain'
        self.response.out.write('It works')

class Processer(webapp2.RequestHandler):
    def get(self):
        outString=""
        postKey=self.request.get("key")
        postPdf=self.request.get("pdf")
        postClean=self.request.get("clean")
        outTitle=''
        if postKey!=userKey:
            outString='It works'
            self.response.out.write(outString)
            return
        else:
            postUrl=self.request.get("url")
            try:
                result= urlfetch.fetch(postUrl)
                self.response.out.write(outString)
            except:
                result=0
            if result!=0:
                if result.status_code== 200:
                    ###this line solve the <!-- tag problem of some webpage(like sina blog) 
                    tmps=result.content.replace('\xe2\x80\x93','--')
                    try:
                        htmlCode=tmps.decode('utf-8')
                    except:
                        htmlCode=tmps.decode('gbk')
                else:
                    htmlCode=""
                if htmlCode!="":
                    readData = Readability(htmlCode, postUrl)
                    outString=readData.content
                    outTitle=readData.title
                else:
                    outString=''
                    outTitle=''
                if postClean=='0':
                    outString=htmlCode
            else:
                outString=''
                outTitle=''
        if postPdf and postPdf!='0':
            self.response.headers['Content-Type'] = 'application/pdf'
            if postClean!='0':
                outString=u'''<style type="text/css">
                @font-face { 
                font-family: "'''+fontName+'''"; 
                src: url("fonts/'''+fontFile+'''") 
                }
                html { 
                font-family: '''+fontName+'''; 
                } 
</style>'''+u'<html><head><title>'+outTitle+u'</title></head><body>'+u'<h1>'+outTitle+u'</h1>'+outString+u'</body></html>'
            else:
                outString=outString=u'''<style type="text/css">
                @font-face { 
                font-family: "'''+fontName+'''"; 
                src: url("fonts/'''+fontFile+'''") 
                }
                html { 
                font-family: '''+fontName+'''; 
                } 
                </style>'''+outString
            rawData=StringIO(outString.encode('utf-8'))
            output=StringIO()
            pisa.log.setLevel('WARNING') #suppress debug log output
            pdf = pisa.CreatePDF(
            rawData,
            output,
            encoding='utf-8',
            )
            pdfData=pdf.dest.getvalue()        
            self.response.out.write(pdfData)
        else:
            self.response.headers['Content-Type'] = 'text/html'
            if postClean!='0':
                outString=u'<html><head><title>'+outTitle+u'</title></head><body>'+u'<h1>'+outTitle+u'</h1>'+outString+u'</body></html>'
            self.response.out.write(outString)

app=webapp2.WSGIApplication([('/', MainPage),('/trans', Processer)],debug=True)

"""
def main():
    application= webapp.WSGIApplication([('/', MainPage)],debug=True)
    application= webapp.WSGIApplication([('/trans', Processer)],debug=True)
    wsgiref.handlers.CGIHandler().run(application)

if __name__== "__main__":
    main()
"""
