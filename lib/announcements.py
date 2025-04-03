from datetime import datetime

PriorityMap = {
   "low": 1,
   "high": 2,
   "critical": 3
}

def toHumanTime(timestamp_s):
   dt = datetime.fromtimestamp(int(timestamp_s))
   return dt.strftime("%Y-%m-%d %H:%M:%S")

class Announcement(object):
   def __init__(self, data):
      self.id = data['id']
      self.enabled = data['on']
      self.priority = data['priority']
      self.message = data['message']
      self.start = data['start']
      self.end = data['end']

   def __str__(self):
      result = f"   . id: {self.id}, enabled: {self.enabled}\n"
      startAt = toHumanTime(self.start)
      endAt = "N/A"
      if self.end != None and self.end != 0:
         endAt = toHumanTime(self.end)
      result += f"     start at: {startAt}, end at: {endAt}\n"
      result += f"     body: \"{self.message}\"\n"
      result += f"     priority: {self.priority}\n"
      return result

class Announcements(object):
   def __init__(self):
      self.announcements = {}

   def update(self, data):
      for ann in data:
         annObj = Announcement(ann)
         self.announcements[annObj.id] = annObj

   def __str__(self):
      result = " - announcements:\n"
      if not self.announcements:
         result += "   . N/A\n"
         return result

      for annId in self.announcements:
         ann = self.announcements[annId]
         result += f"{str(ann)}\n"
      return result

   def getById(self, cId):
      if cId not in self.announcements:
         return None
      return self.announcements[cId]
