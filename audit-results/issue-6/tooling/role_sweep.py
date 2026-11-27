"""Execute in capture_host.py's interactive namespace. Real UI logins and reads;
role-negative HTTP calls are independent checks, never simulated UI errors.
"""
main_context,main_page=context,page
creds=json.loads((PRIVATE/'credentials.json').read_text())
role_checks=[]
for role in ['viewer','operator','custodian','technician']:
    context=browser.new_context(base_url='http://127.0.0.1:8765',viewport={'width':1280,'height':800},device_scale_factor=1)
    context.set_default_timeout(10000);page=context.new_page();page.goto('http://127.0.0.1:8765')
    field('Account name').fill('audit-'+role);field('Password').fill(creds['audit-'+role]);click('Sign in')
    page.get_by_role('tab',name='People',exact=True).wait_for()
    context.set_extra_http_headers({'X-SentriFace-Session':page.locator('meta[name="sentriface-session-token"]').get_attribute('content')})
    auth=context.request.get('/api/auth/status').json()['user']
    assert auth['roles']==[role]
    cap('UX-01','J24',role+'-shell',role.title())
    tab('People');click('Open Synthetic Alpha');cap('UX-06','J24',role+'-profile',role.title())
    if role=='viewer':
        # Current hero star is exposed even though favorites requires add.
        favorite=page.get_by_role('button',name=re.compile('^(Add|Remove) favorite$')).first
        if favorite.is_enabled():
            favorite.click();page.wait_for_timeout(300);cap('UX-07','J24','viewer-favorite-server-denial',role.title())
    tab('Events');page.locator('.encounter-list-row').first.click();cap('UX-09','J24',role+'-event-actions',role.title())
    if page.get_by_role('tab',name='Settings',exact=True).count():
        tab('Settings');cap('UX-13','J24',role+'-settings',role.title())
        if page.get_by_role('button',name='Backups & restore',exact=True).count():
            click('Backups & restore');cap('UX-13','J24',role+'-backup-actions',role.title())
    denied_endpoint={'viewer':'/api/person-update','operator':'/api/integrity/check','custodian':'/api/users','technician':'/api/person-update'}[role]
    response=context.request.post(denied_endpoint,data={},headers={'Origin':'http://127.0.0.1:8765'})
    role_checks.append({'role':role,'capabilities':auth['capabilities'],'negative_endpoint':denied_endpoint,'http_status':response.status,'result':'PASS' if response.status==403 else 'FAIL'})
    (PRIVATE/'role-checks.json').write_text(json.dumps(role_checks,indent=2))
    assert response.status==403,(role,response.status)
    context.close()
context,page=main_context,main_page
(PRIVATE/'role-checks.json').write_text(json.dumps(role_checks,indent=2))
print('Four non-admin roles exercised; all four independent forbidden-operation checks HTTP403')
