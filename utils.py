
from selenium.webdriver.common.keys import Keys
import time

# Get an element {%{
def get_elements(browser, tag_name=None, id_attr=None, class_attr=None, attrs=dict(), wait=False):
  '''
  This method fetch a node among the DOM based on its attributes.

  You can indicate wether this method is expected to wait for this element to appear.
  '''

  css_selector = ""

  css_selector += tag_name if tag_name is not None else "*"
  css_selector += ("." + class_attr) if class_attr is not None else ""
  css_selector += ("#" + id_attr) if id_attr is not None else ""

  if attrs:
    css_selector += "["
    item_number = 0

    for attr_name, value_attr in attrs.items():
      css_selector += "%(attr)s='%(value)s'" % dict(attr=attr_name, value=value_attr)

      item_number += 1
      if item_number != len(attrs):
        css_selector += ","

    css_selector += "]"

  if not wait:
    elements = browser.find_elements_by_css_selector(css_selector)
  else:
    while True:
      try:
        elements = browser.find_elements_by_css_selector(css_selector)
        if elements:
            break

        print("Wait 4 '%s'" % css_selector)
        time.sleep(1)
      except:
        print("Wait 4 '%s'" % css_selector)
        time.sleep(1)

  return elements

def get_element(browser, tag_name=None, id_attr=None, class_attr=None, attrs=dict(), wait=False, position=None):
  elements = get_elements(browser, tag_name, id_attr, class_attr, attrs, wait)

  if position is None:
      only_visible = filter(lambda x : x.is_displayed(), elements)
      return only_visible[0] if only_visible else elements[0]
  else:
    return elements[position]

def to_camel_case(text):
    words = text.split()
    words = map(lambda x : x[:1].upper() + x[1:].lower(), words)
    return ' '.join(words)

def get_element_from_text(browser, tag_name, text, class_attr='', wait=True):
  '''
  This method fetch a node among the DOM based on its text.

  To find it, you must provide the name of the tag and its text.

  You can indicate wether this method is expected to wait for this element to appear.
  '''
  class_attr = (" and @class = '%s'" % class_attr) if class_attr else ''

  if not isinstance(tag_name, list):
    tag_name = [tag_name]
  possibilities = []

  for my_tag in tag_name:
    data = dict(class_attr=class_attr, tagname=my_tag, text=text)

    xpath1_query = "//%(tagname)s[normalize-space(.)='%(text)s'%(class_attr)s]" % data
    xpath2_query = "//%(tagname)s//*[normalize-space(.)='%(text)s'%(class_attr)s]" % data
    possibilities.append(xpath1_query)
    possibilities.append(xpath2_query)

  xpath_query = '|'.join(possibilities)

  if not wait:
    return browser.find_elements_by_xpath(xpath_query)[0]
  else:
    while True:
      elems = browser.find_elements_by_xpath(xpath_query)
      only_visible = filter(lambda x : x.is_displayed(), elems)

      if elems:
        return only_visible[0] if only_visible else elems[0]

      print("Wait 4 '%s'" % xpath_query)
      time.sleep(1)

def get_column_position_in_table(maintable, columnname):
    elem = get_element_from_text(maintable, tag_name="th", text=columnname)
    parent = elem.parent
    right_pos = None

    for pos, children in enumerate(parent.find_elements_by_tag_name("th")):
        if children.get_attribute("id") == elem.get_attribute("id"):
            right_pos = pos
            break

    return right_pos

def get_table_row_from_hashes(world, keydict):
    columns = keydict.keys()

    maintable = get_element(world.browser, tag_name="table", class_attr="gridview")

    # Reference
    position_per_column = {}
    for column in columns:
        column_normalized = to_camel_case(column)
        pos_in_table = get_column_position_in_table(maintable, column_normalized)
        position_per_column[column] = pos_in_table

    lines = get_elements(maintable, tag_name="tr", class_attr="grid-row")

    # we look for the first line with the right value
    for row_node in lines:

        # we have to check all the columns
        for column, position in position_per_column.iteritems():
            td_node = get_element(row_node, class_attr="grid-cell", tag_name="td", position=position)

            value = keydict[column]
            new_value = convert_input(world, value)

            if td_node.text.strip() != new_value:
                break
        else:
            return row_node

    return None

#}%}

# Wait {%{
def wait_until_no_ajax(browser):
    while True:
        time.sleep(1)
        # sometimes, openobject doesn't exist in some windows
        ret = browser.execute_script('''

            function check(tab){
                for(i in tab){
                    if(tab[i]){
                        return false;
                    }
                }
                return true;
            }

            if(!check(window.TOT)){
                return "BLOCKED IN WINDOW";
            }

            elements = window.document.getElementsByTagName('iframe');

            for(var i = 0; i < elements.length; i++){
                if(!check(elements[i].currentWindow.TOT)){
                    return "BLOCKED IN INFRAME " + i;
                }
            }

            return (typeof openobject == 'undefined') ? 0 : openobject.http.AJAX_COUNT;
        ''')

        #return ((typeof openobject == 'undefined') ? 0 : openobject.http.AJAX_COUNT) +
               #(window.TOT == null ? 0 : window.TOT) +
               #(($("iframe").first().size() == 0 || typeof $("iframe")[0].contentWindow.TOT == 'undefined') ? 0 : $("iframe")[0].contentWindow.TOT)

        if str(ret) != "0":
            print "BOUCLE BLOCK", ret
            continue

        return

def repeat_until_no_exception(action, exception, *params):
    while True:
        try:
            return action(*params)
        except exception:
            time.sleep(1)

def wait_until_element_does_not_exist(browser, get_elem):
  '''
  This method tries to click on the elem(ent) until the click doesn't raise en exception.
  '''

  while True:
    try:
      if not get_elem() or not get_elem().is_displayed():
        return
    except Exception as e:
      return
    time.sleep(1)

def wait_until_not_displayed(browser, get_elem, accept_failure=False):
  '''
  This method tries to click on the elem(ent) until the click doesn't raise en exception.
  '''

  while True:
    try:
      elem = get_elem()
      if not elem.is_displayed():
        return
    except Exception as e:
      if accept_failure:
        return
      else:
        print(e)
        raise
    time.sleep(1)

def wait_until_not_loading(browser, wait=True):
  wait_until_not_displayed(browser, lambda : get_element(browser, tag_name="div", id_attr="ajax_loading", wait=wait), accept_failure=not wait)
#}%}

def convert_input(world, content):
    return content.replace("{{ID}}", str(world.idrun))

# Do something {%{
def click_on(elem_fetcher):
  '''
  This method tries to click on the elem(ent) until the click doesn't raise en exception.
  '''

  while True:
    try:
      elem = elem_fetcher()
      if elem and elem.is_displayed():
        elem.click()
      return
    except Exception as e:
      print(e)
      pass
    time.sleep(1)

def action_write_in_element(txtinput, content):
    txtinput.clear()
    txtinput.send_keys((100*Keys.BACKSPACE) + content + Keys.TAB)

def action_select_option(txtinput, content):
    option = get_element_from_text(txtinput, tag_name="option", text=content, wait=True)
    option.click()

def select_in_field_an_option(browser, fieldelement, content, confirm=True, action=action_write_in_element):
    '''
    Find a field according to its label
    '''

    field = fieldelement()
    idattr = field.get_attribute("id")

    value_before = None
    ## we look for the value before (to check after)
    end_value = "_text"
    if idattr[-len(end_value):] == end_value:
        idvalue_before = idattr[:-len(end_value)]
        txtidinput = get_element(browser, id_attr=idvalue_before.replace('/', '\\/'), wait=True)
        value_before = txtidinput.get_attribute("value")

    txtinput = fieldelement()

    action(txtinput, content)

    if confirm:

        # We have to wait until the value is updated in the field
        if value_before is not None:
            value_after = value_before
            while value_after == value_before:
                txtidinput = get_element(browser, id_attr=idvalue_before.replace('/', '\\/'), wait=True)
                value_after = txtidinput.get_attribute("value")

                #click_on(lambda : get_element_from_text(browser, tag_name="span", text=content, wait=True))
        else:
            #FIXME: What happens if the name already exist in the interface?
            #click_on(lambda : get_element_from_text(browser, tag_name="span", text=content, wait=True))
            pass

        # the popup menu should disappear
        #wait_until_element_does_not_exist(browser, get_element_from_text(browser, tag_name="span", text=content))

    # We have to wait until the information is completed
    wait_until_no_ajax(browser)
#}%}
