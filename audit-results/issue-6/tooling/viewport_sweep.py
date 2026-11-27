"""Execute in capture host namespace; equivalence sampling, no UI mutation mocks."""
for width,height,theme in [(1366,768,'light'),(1280,800,'dark'),(900,700,'dark'),(1440,900,'dark')]:
    page.set_viewport_size({'width':width,'height':height})
    if page.locator('html').get_attribute('data-mantine-color-scheme')!=theme:
        click('Switch to '+theme+' mode')
    for name,ux in [('Check a photo','UX-02'),('Review photos','UX-03'),('People','UX-05'),('Events','UX-09'),('World','UX-11'),('Settings','UX-13')]:
        tab(name)
        if name=='People' and page.get_by_role('button',name='Back to people',exact=True).count():click('Back to people')
        if name=='World':page.get_by_role('radiogroup',name='World experience').get_by_text('Explore',exact=True).click()
        if name=='Settings':click('License & activation')
        cap(ux,'J26',f'{width}x{height}-{theme}-{name.replace(" ","-")}')
        if name=='World' and width==900:
            records_list=page.locator('.explore-record')
            if records_list.count():records_list.first.click()
            for label in ['Canvas','Details']:
                page.get_by_role('radiogroup',name='Explore panel').get_by_text(label,exact=True).click()
                cap('UX-11','J26','900x700-dark-Explore-'+label)
page.set_viewport_size({'width':1440,'height':900})
click('Switch to light mode')
print('Viewport/theme equivalence sample finished')
