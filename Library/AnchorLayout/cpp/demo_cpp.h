#ifndef FORMMAIN_H
#define FORMMAIN_H

#include <string>
#include <QMainWindow>

#include "anchorlayout.h"

QT_BEGIN_NAMESPACE
namespace Ui { class FormMain; }
QT_END_NAMESPACE

class FormMain : public QMainWindow
{
    Q_OBJECT

public:
    FormMain(QWidget *parent = nullptr);
    ~FormMain();


private:
    Ui::FormMain *ui;
    AnchorLayout *anchorlayout=NULL;

    void resizeEvent(QResizeEvent *event);
};
#endif // FORMMAIN_H
