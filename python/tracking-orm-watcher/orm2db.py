from sqlalchemy import create_engine, Column, Integer, String
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

Base = declarative_base()

class PipelineTracking(Base):
    __tablename__ = 'pipeline_tracking'

    id = Column(Integer, primary_key=True)
    filename = Column(String)
    status = Column(String)
    retry = Column(Integer)
    #run_count = Column(Integer)

    def __repr__(self):
        return f"<PipelineTracking(filename='{self.filename}', status='{self.status}', retry={self.retry}, run_count={self.run_count})>"

class SQLiteTracking:
    def __init__(self, db_file):
        self.engine = create_engine(f'sqlite:///{db_file}')
        Base.metadata.create_all(self.engine)
        Session = sessionmaker(bind=self.engine)
        self.session = Session()

    def update_tracking(self, filename, status, retry): #,run_count):
        record = self.session.query(PipelineTracking).filter_by(filename=filename).first()
        if record:
            record.status = status
            record.retry = retry
            #record.run_count = run_count
        else:
            record = PipelineTracking(filename=filename, status=status, retry=retry) #, run_count=run_count)
            self.session.add(record)
        self.session.commit()

    def __del__(self):
        self.session.close()
