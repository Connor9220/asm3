#!/usr/bin/python

import additional
import al
import animal
import configuration
import dbfs
import diary
import log
import media
import utils
from i18n import _, after, now, python2display, subtract_years, add_days, date_diff

def get_waitinglist_query(dbo):
    """
    Returns the SELECT and JOIN commands necessary for selecting
    waiting list rows with resolved lookups.
    """
    return "SELECT a.*, a.ID AS WLID, " \
        "s.SpeciesName AS SpeciesName, sz.Size AS SizeName, " \
        "o.OwnerName, o.OwnerSurname, o.OwnerForeNames, o.OwnerTitle, o.OwnerInitials, " \
        "o.OwnerAddress, o.OwnerTown, o.OwnerCounty, o.OwnerPostcode, " \
        "o.HomeTelephone, o.WorkTelephone, o.MobileTelephone, o.EmailAddress, " \
        "u.Urgency AS UrgencyName, " \
        "web.ID AS WebsiteMediaID, " \
        "web.MediaName AS DocMediaName, " \
        "web.Date AS DocMediaDate, " \
        "web.MediaName AS WebsiteMediaName, " \
        "web.Date AS WebsiteMediaDate, " \
        "web.MediaNotes AS WebsiteMediaNotes " \
        "FROM animalwaitinglist a " \
        "LEFT OUTER JOIN lksize sz ON sz.ID = a.Size " \
        "LEFT OUTER JOIN media web ON web.LinkID = a.ID AND web.LinkTypeID = %d AND web.WebsitePhoto = 1 " \
        "INNER JOIN species s ON s.ID = a.SpeciesID " \
        "INNER JOIN owner o ON o.ID = a.OwnerID " \
        "INNER JOIN lkurgency u ON u.ID = a.Urgency" % media.WAITINGLIST

def get_waitinglist_by_id(dbo, wid):
    """
    Returns a single waitinglist record for the ID given
    """
    l = dbo.locale
    r = dbo.first_row( dbo.query( get_waitinglist_query(dbo) + " WHERE a.ID = ?", [wid]) )
    if not r: return None
    ranks = get_waitinglist_ranks(dbo)
    if r.WLID in ranks:
        r.RANK = ranks[r.WLID]
    else:
        r.RANK = ""
    r.TIMEONLIST = date_diff(l, r.DATEPUTONLIST, now(dbo.timezone))
    return r

def get_person_name(dbo, wid):
    """
    Returns the contact name for the waitinglist with id
    """
    return dbo.query_string("SELECT o.OwnerName FROM animalwaitinglist a INNER JOIN owner o ON a.OwnerID = o.ID WHERE a.ID = ?", [wid])

def get_waitinglist_ranks(dbo):
    """
    Returns a dictionary of waiting list IDs with their current ranks.
    """
    byspecies = configuration.waiting_list_rank_by_species(dbo)
    if not byspecies:
        rows = dbo.query("SELECT a.ID, a.SpeciesID FROM animalwaitinglist a " \
            "INNER JOIN owner o ON a.OwnerID = o.ID " \
            "WHERE a.DateRemovedFromList Is Null " \
            "ORDER BY a.Urgency, a.DatePutOnList")
    else:
        rows = dbo.query("SELECT a.ID, a.SpeciesID FROM animalwaitinglist a " \
            "INNER JOIN owner o ON a.OwnerID = o.ID " \
            "WHERE a.DateRemovedFromList Is Null " \
            "ORDER BY a.SpeciesID, a.Urgency, a.DatePutOnList")
    ranks = {}
    lastspecies = 0
    rank = 1
    for r in rows:
        if byspecies:
            if not lastspecies == r.SPECIESID:
                lastspecies = r.SPECIESID
                rank = 1
        ranks[r.ID] = rank
        rank += 1
    return ranks

def get_waitinglist(dbo, priorityfloor = 5, species = -1, size = -1, addresscontains = "", includeremoved = 0, namecontains = "", descriptioncontains = "", siteid = 0):
    """
    Retrieves the waiting list
    priorityfloor: The lowest urgency to show (1 = urgent, 5 = lowest)
    species: A species filter or -1 for all
    size: A size filter or -1 for all
    addresscontains: A partial address
    includeremoved: Whether or not to include removed entries
    namecontains: A partial name
    descriptioncontains: A partial description
    """
    l = dbo.locale

    ands = []
    values = []
    def add(a, v = None):
        ands.append(a)
        if v: values.append(v)
    
    add("a.Urgency <= ?", priorityfloor)
    if includeremoved == 0: add("a.DateRemovedFromList Is Null")
    if species != -1: add("a.SpeciesID = ?", species)
    if size != -1: add("a.Size = ?", size)
    if addresscontains != "": add("UPPER(OwnerAddress) LIKE ?", "%%%s%%" % addresscontains.upper())
    if namecontains != "": add("UPPER(OwnerName) LIKE ?", "%%%s%%" % namecontains.upper())
    if descriptioncontains != "": add("UPPER(AnimalDescription) LIKE ?", "%%%s%%" % descriptioncontains.upper())
    if siteid != 0: add("(o.SiteID = 0 OR o.SiteID = ?)", siteid)

    sql = "%s WHERE %s ORDER BY a.Urgency, a.DatePutOnList" % (get_waitinglist_query(dbo), " AND ".join(ands))
    rows = dbo.query(sql, values)

    wlh = configuration.waiting_list_highlights(dbo).split(" ")
    ranks = get_waitinglist_ranks(dbo)
    for r in rows:
        r.HIGHLIGHT = ""
        for hi in wlh:
            if hi != "":
                if hi.find("|") == -1:
                    wid = hi
                    h = "1"
                else:
                    wid, h = hi.split("|")
                if wid == str(r.WLID).strip():
                    r.HIGHLIGHT = h
                    break
        if r.WLID in ranks:
            r.RANK = ranks[r.WLID]
        else:
            r.RANK = ""
        r.TIMEONLIST = date_diff(l, r.DATEPUTONLIST, now(dbo.timezone))
    return rows

def get_waitinglist_find_simple(dbo, query = "", limit = 0, siteid = 0):
    """
    Returns rows for simple waiting list searches.
    query: The search criteria
    """
    ss = utils.SimpleSearchBuilder(dbo, query)

    sitefilter = ""
    if siteid != 0: sitefilter = " AND (o.SiteID = 0 OR o.SiteID = %d)" % siteid

    # If no query has been given, do a current waitinglist search
    if query == "":
        return get_waitinglist(dbo)
    if utils.is_numeric(query): ss.add_field_value("a.ID", utils.cint(query))
    ss.add_field("o.OwnerName")
    ss.add_clause("EXISTS(SELECT ad.Value FROM additional ad " \
        "INNER JOIN additionalfield af ON af.ID = ad.AdditionalFieldID AND af.Searchable = 1 " \
        "WHERE ad.LinkID=a.ID AND ad.LinkType IN (%s) AND LOWER(ad.Value) LIKE ?)" % additional.WAITINGLIST_IN)
    ss.add_large_text_fields([ "a.AnimalDescription", "a.ReasonForWantingToPart", "a.ReasonForRemoval" ])

    sql = "%s WHERE a.ID > 0 %s AND (%s) ORDER BY a.ID" % (get_waitinglist_query(dbo), sitefilter, " OR ".join(ss.ors))
    return dbo.query(sql, ss.values, limit=limit, distincton="ID")

def get_satellite_counts(dbo, wlid):
    """
    Returns a resultset containing the number of each type of satellite
    record that a waitinglist entry has.
    """
    return dbo.query("SELECT a.ID, " \
        "(SELECT COUNT(*) FROM media me WHERE me.LinkID = a.ID AND me.LinkTypeID = ?) AS media, " \
        "(SELECT COUNT(*) FROM diary di WHERE di.LinkID = a.ID AND di.LinkType = ?) AS diary, " \
        "(SELECT COUNT(*) FROM log WHERE log.LinkID = a.ID AND log.LinkType = ?) AS logs " \
        "FROM animalwaitinglist a WHERE a.ID = ?", (media.WAITINGLIST, diary.WAITINGLIST, log.WAITINGLIST, wlid))

def delete_waitinglist(dbo, username, wid):
    """
    Deletes a waiting list record
    """
    dbo.delete("media", "LinkID=%d AND LinkTypeID=%d" % (wid, media.WAITINGLIST), username)
    dbo.delete("diary", "LinkID=%d AND LinkType=%d" % (wid, diary.WAITINGLIST), username)
    dbo.delete("log", "LinkID=%d AND LinkType=%d" % (wid, log.WAITINGLIST), username)
    dbo.execute("DELETE FROM additional WHERE LinkID = %d AND LinkType IN (%s)" % (wid, additional.WAITINGLIST_IN))
    dbo.delete("animalwaitinglist", wid, username)
    dbfs.delete_path(dbo, "/waitinglist/%d" % wid)

def send_email_from_form(dbo, username, post):
    """
    Sends an email to a lost/found person from a posted form. Attaches it as
    a log entry if specified.
    """
    emailfrom = post["from"]
    emailto = post["to"]
    emailcc = post["cc"]
    emailbcc = post["bcc"]
    subject = post["subject"]
    ishtml = post.boolean("html")
    addtolog = post.boolean("addtolog")
    logtype = post.integer("logtype")
    body = post["body"]
    rv = utils.send_email(dbo, emailfrom, emailto, emailcc, emailbcc, subject, body, ishtml == 1 and "html" or "plain")
    if addtolog == 1:
        log.add_log(dbo, username, log.WAITINGLIST, post.integer("wlid"), logtype, body)
    return rv

def update_waitinglist_remove(dbo, username, wid):
    """
    Marks a waiting list record as removed
    """
    dbo.update("animalwaitinglist", wid, { "DateRemovedFromList": dbo.today() }, username)

def update_waitinglist_highlight(dbo, wlid, himode):
    """
    Toggles a waiting list ID record as highlighted.
    wlid: The waiting list id to toggle
    himode: a highlight value from 1 to 5 for a colour
    """
    hl = list(configuration.waiting_list_highlights(dbo).split(" "))
    wlid = str(wlid).strip()
    # Create a new highlight list that doesn't have our id in it
    nl = []
    removed = False
    for hi in hl:
        if hi != "":
            if hi.find("|") != -1:
                wid, h = hi.split("|")
            else:
                wid = hi
                h = "1"
            if wlid == wid:
                removed = True
            else:
                nl.append(wid + "|" + h)
    # If our id wasn't present in the list, add it (so we're
    # effectively toggling the id on and off)
    if not removed:
        nl.append(wlid + "|" + himode)
    configuration.waiting_list_highlights(dbo, " ".join(nl))

def auto_remove_waitinglist(dbo):
    """
    Finds and automatically marks entries removed that have gone past
    the last contact date + weeks.
    """
    l = dbo.locale
    rows = dbo.query("SELECT a.ID, a.DateOfLastOwnerContact, " \
        "a.AutoRemovePolicy " \
        "FROM animalwaitinglist a WHERE a.DateRemovedFromList Is Null " \
        "AND AutoRemovePolicy > 0 AND DateOfLastOwnerContact Is Not Null")
    updates = []
    for r in rows:
        xdate = add_days(r.DATEOFLASTOWNERCONTACT, 7 * r.AUTOREMOVEPOLICY)
        if after(now(dbo.timezone), xdate):
            al.debug("auto removing waitinglist entry %d due to policy" % r.ID, "waitinglist.auto_remove_waitinglist", dbo)
            updates.append((now(dbo.timezone), _("Auto removed due to lack of owner contact.", l), r.ID))
    if len(updates) > 0:
        dbo.execute_many("UPDATE animalwaitinglist SET DateRemovedFromList = ?, " \
            "ReasonForRemoval=? WHERE ID=?", updates)
        
def auto_update_urgencies(dbo):
    """
    Finds all animals where the next UrgencyUpdateDate field is greater
    than or equal to today and the urgency is larger than High (so we
    can never reach Urgent).
    """
    update_period_days = configuration.waiting_list_urgency_update_period(dbo)
    if update_period_days == 0:
        al.debug("urgency update period is 0, not updating waiting list entries", "waitinglist.auto_update_urgencies", dbo)
        return
    rows = dbo.query("SELECT a.* " \
        "FROM animalwaitinglist a WHERE UrgencyUpdateDate <= ? " \
        "AND Urgency > 2", [dbo.today()])
    updates = []
    for r in rows:
        al.debug("increasing urgency of waitinglist entry %d" % r.ID, "waitinglist.auto_update_urgencies", dbo)
        updates.append((now(dbo.timezone), add_days(r.URGENCYUPDATEDATE, update_period_days), r.URGENCY - 1, r.ID))
    if len(updates) > 0:
        dbo.execute_many("UPDATE animalwaitinglist SET " \
            "UrgencyLastUpdatedDate=?, " \
            "UrgencyUpdateDate=?, " \
            "Urgency=? " \
            "WHERE ID=? ", updates)
            
def update_waitinglist_from_form(dbo, post, username):
    """
    Updates a waiting list record from the screen
    data: The webpy data object containing form parameters
    """
    l = dbo.locale
    wlid = post.integer("id")

    if not dbo.optimistic_check("animalwaitinglist", post.integer("id"), post.integer("recordversion")):
        raise utils.ASMValidationError(_("This record has been changed by another user, please reload.", l))

    if post["description"] == "":
        raise utils.ASMValidationError(_("Description cannot be blank", l))
    if post.integer("owner") == 0:
        raise utils.ASMValidationError(_("Waiting list entries must have a contact", l))
    if post["dateputon"] == "":
        raise utils.ASMValidationError(_("Date put on cannot be blank", l))

    dbo.update("animalwaitinglist", wlid, {
        "SpeciesID":                post.integer("species"),
        "Size":                     post.integer("size"),
        "DatePutOnList":            post.date("dateputon"),
        "OwnerID":                  post.integer("owner"),
        "AnimalDescription":        post["description"],
        "ReasonForWantingToPart":   post["reasonforwantingtopart"],
        "CanAffordDonation":        post.boolean("canafforddonation"),
        "Urgency":                  post.integer("urgency"),
        "DateRemovedFromList":      post.date("dateremoved"),
        "AutoRemovePolicy":         post.integer("autoremovepolicy"),
        "DateOfLastOwnerContact":   post.date("dateoflastownercontact"),
        "ReasonForRemoval":         post["reasonforremoval"],
        "Comments":                 post["comments"]
    }, username)

    additional.save_values_for_link(dbo, post, wlid, "waitinglist")

def insert_waitinglist_from_form(dbo, post, username):
    """
    Creates a waiting list record from the screen
    data: The webpy data object containing form parameters
    """
    l = dbo.locale
    if post["description"] == "":
        raise utils.ASMValidationError(_("Description cannot be blank", l))
    if post.integer("owner") == 0:
        raise utils.ASMValidationError(_("Waiting list entries must have a contact", l))
    if post["dateputon"] == "":
        raise utils.ASMValidationError(_("Date put on cannot be blank", l))

    nwlid = dbo.insert("animalwaitinglist", {
        "SpeciesID":                post.integer("species"),
        "Size":                     post.integer("size"),
        "DatePutOnList":            post.date("dateputon"),
        "OwnerID":                  post.integer("owner"),
        "AnimalDescription":        post["description"],
        "ReasonForWantingToPart":   post["reasonforwantingtopart"],
        "CanAffordDonation":        post.boolean("canafforddonation"),
        "Urgency":                  post.integer("urgency"),
        "DateRemovedFromList":      post.date("dateremoved"),
        "AutoRemovePolicy":         post.integer("autoremovepolicy"),
        "DateOfLastOwnerContact":   post.date("dateoflastownercontact"),
        "ReasonForRemoval":         post["reasonforremoval"],
        "Comments":                 post["comments"],
        "UrgencyLastUpdatedDate":   dbo.today(),
        "UrgencyUpdateDate":        dbo.today(offset=configuration.waiting_list_urgency_update_period(dbo))
    }, username)

    # Save any additional field values given
    additional.save_values_for_link(dbo, post, nwlid, "waitinglist", True)

    return nwlid

def create_animal(dbo, username, wlid):
    """
    Creates an animal record from a waiting list entry with the id given
    """
    l = dbo.locale
    a = dbo.first_row( dbo.query("SELECT * FROM animalwaitinglist WHERE ID = ?", [wlid]) )
    
    data = {
        "animalname":           _("Waiting List {0}", l).format(wlid),
        "markings":             str(a["ANIMALDESCRIPTION"]),
        "reasonforentry":       str(a["REASONFORWANTINGTOPART"]),
        "species":              str(a["SPECIESID"]),
        "hiddenanimaldetails":  str(a["COMMENTS"]),
        "broughtinby":          str(a["OWNERID"]),
        "originalowner":        str(a["OWNERID"]),
        "animaltype":           configuration.default_type(dbo),
        "entryreason":          configuration.default_entry_reason(dbo),
        "breed1":               configuration.default_breed(dbo),
        "breed2":               configuration.default_breed(dbo),
        "basecolour":           configuration.default_colour(dbo),
        "size":                 configuration.default_size(dbo),
        "internallocation":     configuration.default_location(dbo),
        "dateofbirth":          python2display(l, subtract_years(now(dbo.timezone))),
        "estimateddob":         "1"
    }
    # If we aren't showing the time brought in, set it to midnight
    if not configuration.add_animals_show_time_brought_in(dbo):
        data["timebroughtin"] = "00:00:00"

    # If we're creating shelter codes manually, we need to put something unique
    # in there for now. Use the id
    if configuration.manual_codes(dbo):
        data["sheltercode"] = "WL" + str(wlid)
        data["shortcode"] = "WL" + str(wlid)
    nextid, code = animal.insert_animal_from_form(dbo, utils.PostedData(data, l), username)

    # Now that we've created our animal, we should remove this entry from the waiting list
    dbo.update("animalwaitinglist", wlid, { "DateRemovedFromList": dbo.today(), "ReasonForRemoval": _("Moved to animal record {0}", l).format(code) }, username)

    # If there were any logs and media entries on the waiting list, create them on the animal

    # Media
    for me in dbo.query("SELECT * FROM media WHERE LinkTypeID = ? AND LinkID = ?", (media.WAITINGLIST, wlid)):
        ext = me.medianame
        ext = ext[ext.rfind("."):].lower()
        mediaid = dbo.get_id("media")
        medianame = "%d%s" % ( mediaid, ext )
        dbo.insert("media", {
            "ID":                   mediaid,
            "DBFSID":               0,
            "MediaSize":            0,
            "MediaName":            medianame,
            "MediaMimeType":        media.mime_type(medianame),
            "MediaType":            me.mediatype,
            "MediaNotes":           me.medianotes,
            "WebsitePhoto":         me.websitephoto,
            "WebsiteVideo":         me.websitevideo,
            "DocPhoto":             me.docphoto,
            "ExcludeFromPublish":   me.excludefrompublish,
            # ASM2_COMPATIBILITY
            "NewSinceLastPublish":  1,
            "UpdatedSinceLastPublish": 0,
            # ASM2_COMPATIBILITY
            "LinkID":               nextid,
            "LinkTypeID":           media.ANIMAL,
            "Date":                 me.date,
            "RetainUntil":          me.retainuntil
        }, generateID=False)

        # Now clone the dbfs item pointed to by this media item if it's a file
        if me.mediatype == media.MEDIATYPE_FILE:
            filedata = dbfs.get_string(dbo, me.medianame)
            dbfsid = dbfs.put_string(dbo, medianame, "/animal/%d" % nextid, filedata)
            dbo.execute("UPDATE media SET DBFSID = ?, MediaSize = ? WHERE ID = ?", ( dbfsid, len(filedata), mediaid ))

    # Logs
    for lo in dbo.query("SELECT * FROM log WHERE LinkType = ? AND LinkID = ?", (log.WAITINGLIST, wlid)):
        dbo.insert("log", {
            "LinkID":       nextid,
            "LinkType":     log.ANIMAL,
            "LogTypeID":    lo.LOGTYPEID,
            "Date":         lo.DATE,
            "Comments":     lo.COMMENTS
        }, username)

    return nextid
   

