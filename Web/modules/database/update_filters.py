from pymongo import MongoClient
import Web.modules.database.settings as cfg

def get_filter_names():
    client = MongoClient(cfg.MONGODB_HOST, cfg.MONGODB_PORT)
    db = client[cfg.MONGODB_DB]
    names = db.settings.find_one({'setting_type': 'filter_names'})
    client.close()
    if names:
        return names.get('names', {
            '1': 'Fach/Kategorie',
            '2': 'System/Bereich',
            '3': 'Typ/Art'
        })
    return {
        '1': 'Fach/Kategorie',
        '2': 'System/Bereich',
        '3': 'Typ/Art'
    }

def set_filter_name(filter_num, name):
    client = MongoClient(cfg.MONGODB_HOST, cfg.MONGODB_PORT)
    db = client[cfg.MONGODB_DB]
    names = get_filter_names()
    names[str(filter_num)] = name
    db.settings.update_one(
        {'setting_type': 'filter_names'},
        {'$set': {'names': names}},
        upsert=True
    )
    client.close()
    return True
