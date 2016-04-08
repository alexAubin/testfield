#FIXME: The resolution sometimes hides the controls (if it's at the far right)
from credentials import *

from lettuce import *
from selenium import webdriver
from selenium.common.exceptions import StaleElementReferenceException
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import Select
from utils import *
import datetime
import os
import os.path
import re
import tempfile

RESULTS_DIR = 'results/'
ENV_DIR = 'instances/'
FILE_DIR = 'files'

RUN_NUMBER_FILE = 'run'

# Selenium management {%{
@before.all
def connect_to_db():

    #world.browser = webdriver.PhantomJS()
    world.browser = webdriver.Firefox()
    #world.browser = webdriver.Chrome()
    world.browser.set_window_size(1600, 1200)
    world.nbframes = 0

    world.durations = {}

    with open("monkeypatch.js") as f:
        world.monkeypatch = '\r\n'.join(f.readlines())

@before.each_step
def apply_monkey_patch(step):
    world.browser.execute_script(world.monkeypatch)

@before.each_scenario
def update_idrun(scenario):
    world.idrun = 1

    if os.path.isdir(RUN_NUMBER_FILE):
        raise Error("A configuration file is a directory")
    if os.path.isfile(RUN_NUMBER_FILE):
        #FIXME: A file could be huge, it could lead to a memory burst...
        f = open(RUN_NUMBER_FILE)
        try:
            s_idrun = f.read(512)
            last_idrun = int(s_idrun)
            world.idrun = last_idrun + 1
        except ValueError:
            raise Error("Invalid value in %s" % RUN_NUMBER_FILE)

        f.close()

    new_f = open(RUN_NUMBER_FILE, 'w')
    new_f.write(str(world.idrun))
    new_f.close()

@after.each_scenario
def remove_iframes(scenario):
    world.nbframes = 0

@after.all
def disconnect_to_db(total):
    #world.browser = webdriver.PhantomJS()

    printscreen_path = os.path.join(RESULTS_DIR, "last_screen.png")
    content_path = os.path.join(RESULTS_DIR, "last_content.html")

    world.browser.save_screenshot(printscreen_path)

    content = world.browser.page_source
    f = open(content_path, 'w')
    f.write(content.encode('utf-8'))
    f.close()

    world.browser.close()
#}%}

# Log into/out of/restore an instance{%{

@step('I go on the homepage')
def go_home_page(step):
    world.browser.get(HTTP_URL_SERVER)

@step('I log into instance "([^"]*)"')
def connect_on_database(step, database_name):
    # we would like to get back to the the login page
    world.browser.delete_all_cookies()
    world.browser.get(HTTP_URL_SERVER)

    # select the database chosen by the user
    elem_select = get_element(world.browser, tag_name="select", id_attr="db")
    get_element(elem_select, tag_name="option", attrs={'value': database_name}).click()

    # fill in the credentials
    get_element(world.browser, tag_name="input", id_attr="user").send_keys("admin")
    get_element(world.browser, tag_name="input", id_attr="password").send_keys("admin")
    # log in
    get_element(world.browser, tag_name="button", attrs={'type': 'submit'}).click()

@step('I log out')
def log_out(step):
    world.browser.get("%(url)s/openerp/logout" % dict(url=HTTP_URL_SERVER))

def run_script(dbname, script):

    scriptfile = tempfile.mkstemp()
    f = os.fdopen(scriptfile[0], 'w')
    f.write(script)
    f.close()

    os.environ['PGPASSWORD'] = DB_PASSWORD

    ret = os.popen('psql -h %s -U %s %s < %s' % (DB_ADDRESS, DB_USERNAME, dbname, scriptfile[1])).read()

    try:
        os.unlink(scriptfile[1])
    except OSError as e:
        pass

    return ret

@step('I restore environment "([^"]*)"')
def restore_environment(step, env_name):

    # We have to load the environment
    environment_dir = os.path.join(ENV_DIR, env_name)

    try:
        if os.path.isfile(environment_dir):
            raise Exception("%s is a file, not a directory" % environment_dir)
        elif not os.path.isdir(environment_dir):
            raise Exception("%s is not a valid directory" % environment_dir)

        for filename in os.listdir(environment_dir):
            dbname, _ = os.path.splitext(filename)

            if not dbname:
                raise Exception("No database name in %s" % dbname)

            dbtokill = run_script("postgres", '''
                SELECT 'select pg_terminate_backend(' || procpid || ');'
                FROM pg_stat_activity
                WHERE datname = '%s'
            ''' % dbname)

            #FIXME: Need superuser rights... ALTER USER unifield_dev WITH SUPERUSER;
            names = dbtokill.split('\n')
            killall = '\n'.join(names[2:-3]).strip()

            if killall:
                run_script("postgres", killall)

            run_script("postgres", 'DROP DATABASE IF EXISTS "%s"' % dbname)
            run_script('postgres', 'CREATE DATABASE "%s";' % dbname)

            path_dump = os.path.join(environment_dir, filename)
            os.system('pg_restore -h %s -U %s --no-acl --no-owner -d %s %s' % (DB_ADDRESS, DB_USERNAME, dbname, path_dump))

    except (OSError, IOError) as e:
        raise Exception("Unable to access an environment (cause: %s)" % e)

#}%}

# Synchronisation {%{

@step('I synchronize "([^"]*)"')
def synchronize_instance(step, instance_name):

    from oerplib.oerp import OERP
    from oerplib.error import RPCError

    class XMLRPCConnection(OERP):
        '''
        XML-RPC connection class to connect with OERP
        '''

        def __init__(self, db_name):
            '''
            Constructor
            '''
            # Prepare some values
            server_port = NETRPC_PORT
            server_url = URL_SERVER
            uid = 'admin'
            pwd = 'admin'
            # OpenERP connection
            super(XMLRPCConnection, self).__init__(
                server=server_url,
                protocol='xmlrpc',
                port=server_port,
                timeout=3600
            )
            # Login initialization
            self.login(uid, pwd, db_name)

    try:
        connection = XMLRPCConnection(instance_name)

        conn_obj = connection.get('sync.client.sync_server_connection')
        sync_obj = connection.get('sync.client.sync_manager')

        conn_ids = conn_obj.search([])
        conn_obj.action_connect(conn_ids)
        sync_ids = sync_obj.search([])
        sync_obj.sync(sync_ids)
    except RPCError as e:
        raise
#}%}

# Open a menu/tab {%{
@step('I open tab menu "([^"]*)"')
def open_tab(step, tab_to_open):
    tab_to_open_normalized = to_camel_case(tab_to_open)

    elem_menu = get_element(world.browser, tag_name="div", id_attr="applications_menu")
    button_label = get_element_from_text(elem_menu, tag_name="span", text=tab_to_open_normalized)
    button_label.click()

    wait_until_not_loading(world.browser, wait=False)

@step('I open accordion menu "([^"]*)"')
def open_tab(step, menu_to_click_on):

    accordion_node = get_element_from_text(world.browser, tag_name="li", class_attr="accordion-title", text=menu_to_click_on)

    block_element = accordion_node.find_elements_by_xpath("following-sibling::*[1]")[0]

    if block_element.get_attribute("class") != 'accordion-content' or not block_element.is_displayed():
        accordion_node.click()

def open_menu(menu_to_click_on):
    menus = menu_to_click_on.split("|")

    after_pos = 0

    for menu in menus:

        while True:
            elements = get_elements(world.browser, tag_name="tr", class_attr="row")
            visible_elements = filter(lambda x : x.is_displayed(), elements)
            valid_visible_elements = visible_elements[after_pos:]

            text_in_menus = map(lambda x : x.text, valid_visible_elements)

            if menu in text_in_menus:
                #FIXME: It seems that sometimes the click doesn't work
                #  because we wait for submenus to appear although the last
                #  cast hasn't been done.
                pos = text_in_menus.index(menu)

                valid_visible_elements[pos].click()

                after_pos += pos + 1
                break

    wait_until_not_loading(world.browser)

@step('I click on menu "([^"]*)" and open the window$')
def open_tab(step, menu_to_click_on):
    open_menu(menu_to_click_on)

    # we have to open the window!
    world.browser.switch_to_default_content()
    world.browser.switch_to_frame(get_element(world.browser, tag_name="iframe", position=world.nbframes, wait=True))
    world.nbframes += 1
    wait_until_no_ajax(world.browser)

@step('I click on menu "([^"]*)"$')
def open_tab(step, menu_to_click_on):
    open_menu(menu_to_click_on)

# I open tab "Supplier"
@step('I open tab "([^"]*)"')
def open_tab(step, tabtoopen):
    click_on(lambda : get_element_from_text(world.browser, class_attr="tab-title", tag_name="span", text=tabtoopen, wait=True))
    wait_until_not_loading(world.browser)

#}%}

# Fill fields {%{
@step('I fill "([^"]*)" with "([^"]*)"$')
def fill_field(step, fieldname, content):

    # Most of the fields use IDs, however, some of them are included in a table with strange fields.
    #  We have to look for both
    my_input = None

    while not my_input:
        labels = get_elements_from_text(world.browser, tag_name="label", text=fieldname, wait=False)

        # we have a label!
        if labels:
            label = labels[0]
            idattr = label.get_attribute("for")
            my_input = get_element(world.browser, id_attr=idattr.replace('/', '\\/'), wait=True)
            break

        # do we have a strange table?
        table_header = get_elements_from_text(world.browser, class_attr='separator horizontal', tag_name="div", text=fieldname, wait=False)

        if not table_header:
            continue

        # => td
        table_header = table_header[0]

        table_node = table_header.find_elements_by_xpath("ancestor::tr[1]")
        if not table_node:
            continue

        element = table_node[0].find_elements_by_xpath("following-sibling::*[1]")
        if not element:
            continue

        # on peut maintenant trouver un input ou un select!
        for tagname in ["select", "input", "textarea"]:
            inputnode = element[0].find_elements_by_tag_name(tagname)
            if inputnode:
                my_input = inputnode[0]
                break

    if my_input.tag_name == "select":
        #FIXME: Sometimes it doesn't work... the input is not selected
        # or the value is not saved...
        my_input.click()
        click_on(lambda : get_element_from_text(my_input, tag_name="option", text=content, wait=False))
        my_input.click()
    elif my_input.tag_name == "input" and my_input.get_attribute("type") == "file":
        my_input.clear()
        base_dir = os.path.dirname(__file__)
        content_path = os.path.join(base_dir, FILE_DIR, content)

        if not os.path.isfile(content_path):
            raise Exception("%s is not a file" % content_path)
        my_input.send_keys(content_path)
    elif my_input.tag_name == "input" and my_input.get_attribute("type") == "checkbox":

        if content.lower() not in {"yes", "no"}:
            raise Exception("You cannot defined any value except no and yes for a checkbox")

        if content.lower() == "yes":
            if not my_input.is_selected():
                my_input.click()
        else:
            if my_input.is_selected():
                my_input.click()

    elif my_input.get_attribute("autocomplete") == "off" and '_text' in idattr:
        select_in_field_an_option(world.browser, lambda : (get_element(world.browser, id_attr=idattr.replace('/', '\\/'), wait=True), action_write_in_element, True), content)
    else:
        my_input.send_keys((100*Keys.BACKSPACE) + convert_input(world, content))

    wait_until_no_ajax(world.browser)

@step('I fill "([^"]*)" with table:$')
def fill_field(step, fieldname):
    if not step.hashes:
        raise Exception("Why don't you defined at least one row?")

    TEMP_FILENAME = 'tempfile'

    base_dir = os.path.dirname(__file__)
    content_path = os.path.join(base_dir, FILE_DIR, TEMP_FILENAME)
    f = open(content_path, 'w')

    f.write('<?xml version="1.0"?>')
    f.write('<ss:Workbook xmlns:ss="urn:schemas-microsoft-com:office:spreadsheet">')
    f.write('<ss:Worksheet ss:Name="Sheet1">')
    f.write('<ss:Table>')

    for row in step.hashes:
        f.write('<ss:Row>')
        for cell in row:
            f.write('<ss:Cell>')
            f.write('<ss:Data ss:Type="String">%s</ss:Data>' % cell)
            f.write('</ss:Cell>')
        f.write('</ss:Row>')

    f.write('</ss:Table>')
    f.write('</ss:Worksheet>')
    f.write('</ss:Workbook>')
    f.close()

    step.given('I fill "%s" with "%s"' % (fieldname, TEMP_FILENAME))

#}%}

# I click on ... {%{
# I click on "Search/New/Clear"
@step('I click on "([^"]*)"$')
def click_on_button(step, button):
    world.take_printscren_before = True

    elem = get_element_from_text(world.browser, tag_name=["button", "a"], text=button, wait=True)

    click_on(lambda : get_element_from_text(world.browser, tag_name=["button", "a"], text=button, wait=True))

    if world.nbframes != 0:
        wait_until_not_loading(world.browser, wait=False)

        world.browser.switch_to_default_content()
        world.browser.switch_to_frame(get_element(world.browser, tag_name="iframe", wait=True))

        wait_until_not_loading(world.browser, wait=False)
        wait_until_no_ajax(world.browser)
    else:
        wait_until_not_loading(world.browser, wait=False)
        wait_until_no_ajax(world.browser)

#FIXME: What happens if I want to select several lines?
@step('I click on "([^"]*)" and open the window$')
def click_on_button_and_open(step, button):
    world.take_printscren_before = True

    #FIXME: It seems that two frames block everything... tocheck...
    wait_until_not_loading(world.browser, wait=False)
    wait_until_no_ajax(world.browser)
    click_on(lambda : get_element_from_text(world.browser, tag_name="button", text=button, wait=True))
    #FIXME: It seems that two frames block everything... tocheck...
    wait_until_not_loading(world.browser, wait=False)

    world.browser.switch_to_default_content()
    world.browser.switch_to_frame(get_element(world.browser, position=world.nbframes, tag_name="iframe", wait=True))
    world.nbframes += 1

    wait_until_no_ajax(world.browser)

#FIXME: What happens if I want to select several lines?
# I click on "Save & Close"
@step('I click on "([^"]*)" and close the window$')
def click_on_button_and_close(step, button):
    world.take_printscren_before = True

    click_on(lambda : get_element_from_text(world.browser, tag_name=["button", "a"], text=button, wait=True))
    world.nbframes -= 1

    world.browser.switch_to_default_content()
    if world.nbframes > 0:
        world.browser.switch_to_frame(get_element(world.browser, position=world.nbframes-1, tag_name="iframe", wait=True))
    else:
        wait_until_element_does_not_exist(world.browser, lambda : get_element(world.browser, tag_name="iframe"))

    #wait_until_not_loading(world.browser)
    wait_until_no_ajax(world.browser)

def click_if_toggle_button_is(btn_name, from_class_name):
    btn_name = to_camel_case(btn_name)
    btn_toggle = get_element_from_text(world.browser, tag_name="button", text=btn_name, class_attr=from_class_name, wait=True)
    elem = btn_toggle.get_attribute("class")
    classes = map(lambda x : x.strip(), elem.split())

    btn_toggle.click()
    wait_until_not_loading(world.browser)

@step('I toggle on "([^"]*)"$')
def toggle_on(step, button):
    click_if_toggle_button_is(button, "filter_with_icon inactive")

@step('I toggle off "([^"]*)"$')
def toggle_off(step, button):
    click_if_toggle_button_is(button, "filter_with_icon active")

#}%}

# Check messages (error, warning, ...) {%{
@step('I should see "([^"]*)" in "([^"]*)"')
def should_see(step, content, fieldname):
    label = get_element_from_text(world.browser, tag_name="label", text=fieldname, wait=True)
    idattr = label.get_attribute("for")

    txtinput = get_element(world.browser, id_attr=idattr.replace('/', '\\/'), wait=True)

@step('I should see "([^"]*)"')
def see_message(step, text_to_see):
    e = get_element_from_text(world.browser, tag_name="th", text=text_to_see, wait=True)

@step('I should see a text status with "([^"]*)"')
def see_status(step, message_to_see):
    wait_until_not_loading(world.browser)
    elem = get_element(world.browser, tag_name="tr", id_attr="actions_row", wait=True)

    parts = message_to_see.split('*')
    parts = map(lambda x : re.escape(x), parts)
    reg = '.*' + '.*'.join(parts) + '.*'

    if re.match(reg, elem.text, flags=re.DOTALL) is None:
        print "No '%s' found in '%s'" % (message_to_see, elem.text)
        raise Exception("No '%s' found in '%s'" % (message_to_see, elem.text))

@step('I should see a popup with "([^"]*)"$')
def see_popup(step, message_to_see):
    wait_until_not_loading(world.browser)
    elem = get_element(world.browser, tag_name="td", class_attr="error_message_content", wait=True)

    parts = message_to_see.split('*')
    parts = map(lambda x : re.escape(x), parts)
    reg = '.*' + '.*'.join(parts) + '.*'

    if re.match(reg, elem.text, flags=re.DOTALL) is None:
        print "No '%s' found in '%s'" % (message_to_see, elem.text)
        raise Exception("No '%s' found in '%s'" % (message_to_see, elem.text))
#}%}

# Table management {%{

@step('I fill "([^"]*)" within column "([^"]*)"')
def fill_column(step, content, fieldname):
    gridtable = get_element(world.browser, tag_name="table", class_attr="grid")
    right_pos = get_column_position_in_table(gridtable, fieldname)

    def get_text_box():
        row_in_edit_mode = get_element(world.browser, tag_name="tr", class_attr="editors", wait=True)

        td_node = get_element(row_in_edit_mode, class_attr="grid-cell", tag_name="td", position=right_pos)

        # do we a select at our disposal?
        a_select = get_elements(td_node, tag_name="select")

        if a_select:
            return a_select[0], action_select_option, False
        else:
            my_input = get_element(td_node, tag_name="input", attrs={'type': 'text'})
            
            if my_input.get_attribute("autocomplete") == "off":
                return my_input, action_write_in_element, True
            else:
                return my_input, action_write_in_element, False

        return get_element(td_node, tag_name="input", attrs={'type': 'text'})

    select_in_field_an_option(world.browser, get_text_box, content)

#TODO: Raise an exception if no action is found!
@step('I click "([^"]*)" on line:')
def click_on_line(step, action):
    values = step.hashes
    #TODO: We should be allowed to use more than one value
    if len(step.hashes) != 1:
        raise Exception("You cannot click on more than one line")

    def try_to_click_on_line(step, action):
        row_nodes = get_table_row_from_hashes(world, step.hashes[0])


        for row_node in row_nodes:
            # we have to look for this action the user wants to execute
            if action == 'checkbox':
                actions_to_click = get_elements(row_node, tag_name="input", attrs=dict(type='checkbox'))
            else:
                actions_to_click = get_elements(row_node, attrs={'title': action})

            if not actions_to_click:
                continue

            # we choose an action with the right title randomly...
            action_to_click = actions_to_click[0]
            action_to_click.click()
            wait_until_not_loading(world.browser, wait=False)
            wait_until_no_ajax(world.browser)
            break

    repeat_until_no_exception(try_to_click_on_line, StaleElementReferenceException, step, action)

@step('I click "([^"]*)" on line and open the window:')
def click_on_line_and_open_the_window(step, action):
    click_on_line(step, action)

    world.browser.switch_to_default_content()
    world.browser.switch_to_frame(get_element(world.browser, tag_name="iframe", position=world.nbframes, wait=True))
    world.nbframes += 1

    wait_until_no_ajax(world.browser)

@step('I should see in the main table the following data:')
def check_line(step):
    values = step.hashes

    def try_to_check_line(step):
        for hashes in values:
            #TODO: Check that we don't find twice the same row...
            #TODO: Check that all the lines are in the same table...
            if get_table_row_from_hashes(world, hashes) is None:
                raise Exception("I don't find: %s" % hashes)

    repeat_until_no_exception(try_to_check_line, StaleElementReferenceException, step)

@step('I click "([^"]*)" in the side panel$')
def open_side_panel(step, menuname):
    wait_until_no_ajax(world.browser)
    wait_until_not_loading(world.browser)

    #TODO: Check that the number of frames equal 0, otherwise it doesn't make sense
    element = get_element(world.browser, id_attr="a_main_sidebar", wait=True)

    if 'closed' in element.get_attribute("class"):
        element.click()

    elem = get_element_from_text(world.browser, tag_name="a", text=menuname)
    elem.click()

    wait_until_not_loading(world.browser)

@step('I click "([^"]*)" in the side panel and open the window$')
def open_side_panel_and_open(step, menuname):

    open_side_panel(step, menuname)

    world.browser.switch_to_default_content()
    world.browser.switch_to_frame(get_element(world.browser, tag_name="iframe", position=world.nbframes, wait=True))
    world.nbframes += 1

    wait_until_no_ajax(world.browser)

@step('I validate the line')
def choose_field(step):
    click_on(lambda : get_element(world.browser, tag_name="img", attrs={'title': 'Update'}, wait=True))
    wait_until_no_ajax(world.browser)
    wait_until_not_loading(world.browser)

#}%}

# Debugging steps {%{
@step('I sleep')
def selenium_sleeps(step):
    import time
    time.sleep(400)

#}%}

# Time evaluators {%{

@step('I store the time difference in "([^"]*)"')
def save_time_difference(step, counter):
    step.need_printscreen = False
    now = datetime.datetime.now()
    total_secs = (now - world.last_measure).total_seconds()
    world.durations[counter] = total_secs

@step('I save the time')
def save_time(step):
    step.need_printscreen = False
    world.last_measure = datetime.datetime.now()

@step('I store the values for "([^"]*)" in "([^"]*)"')
def save_time_results(step, counters, filename):
    step.need_printscreen = False
    values = []

    if 'COUNT' in os.environ:
        values.append(os.environ['COUNT'])

    for counter in counters.split():
        values.append(str(world.durations.get(counter, '')))

    results_path = os.path.join(RESULTS_DIR, filename)

    # let's create a title
    ret = ['COUNT'] if 'COUNT' in os.environ else []
    ret += counters.split()
    first_line = ';'.join(ret)
    has_to_add_title = True

    # we have to read the last line to check if a header has to be added
    if os.path.isfile(results_path):
        with open(results_path, 'r') as f:
            lines = f.readlines()

            if lines and lines[0].strip() == first_line.strip():
                has_to_add_title = False

    f = open(results_path, 'a')
    if has_to_add_title:
        f.write(first_line)

    line = ';'.join(values)
    f.write('\r\n' + line)
    f.close()

#}%}

