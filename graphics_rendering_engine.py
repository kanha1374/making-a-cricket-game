import tkinter as tk

class CricketGame:
    def __init__(self, root):
        self.root = root
        self.root.title("Cricket Game")
        self.canvas = tk.Canvas(root, width=800, height=600, bg='green')
        self.canvas.pack()
        self.setup_field()
        self.setup_ui()

    def setup_field(self):
        # Draw the field
        # Placeholder for field rendering code
        self.canvas.create_oval(50, 50, 750, 550, fill='lightgreen')

    def setup_ui(self):
        # Setup UI elements like buttons
        self.start_button = tk.Button(self.root, text='Start Match', command=self.start_match)
        self.start_button.pack(side='bottom')

    def start_match(self):
        # Placeholder for match start logic
        self.canvas.create_text(400, 300, text='Match Started!', font=('Arial', 24), fill='white')

if __name__ == '__main__':
    root = tk.Tk()
    game = CricketGame(root)
    root.mainloop()