from nimsgears.model import *
import transaction
import os

init_model(sqlalchemy.create_engine('postgresql://nims:nims@cnifs.stanford.edu:5432/nims'))

go = True

cur_id=-1

while go:
    d = Dataset.query.filter(Dataset.kind==u'qa').filter(Dataset.id>cur_id).order_by(Dataset.id).first()
    cur_id = d.id
    file_dir = '/net/cnifs/cnifs/nims/'+d.relpath
    changed = False
    for i,f in enumerate(d.filenames):
        fn,ext = os.path.splitext(f.encode())
        if fn=='qa_report':
            new_name = d.container.name+'_qa'+ext
            print(os.path.join(file_dir,f), os.path.join(file_dir,new_name))
            os.rename(os.path.join(file_dir,f), os.path.join(file_dir,new_name))
            d.filenames[i] = new_name.decode()
            changed = True
    if changed:
        transaction.commit()


